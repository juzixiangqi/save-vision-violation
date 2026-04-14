from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional
from app.services.video_stream import stream_manager
from app.services.redis_client import redis_client
from app.services.rabbitmq_client import rabbitmq_client
from app.config.manager import config_manager
from app.core.detector import YOLODetector
from app.core.tracker import SimpleTracker
from app.core.state_machine import StateMachine, PersonState
from app.core.zone_manager import zone_manager
from app.core.debug_visualizer import process_video_frame_debug
import cv2
import numpy as np
import base64
from io import BytesIO

router = APIRouter(prefix="/api/monitor", tags=["monitor"])

# 全局组件
detector: YOLODetector = None
tracker: SimpleTracker = None
state_machine: StateMachine = None


def init_components():
    """初始化检测组件"""
    global detector, tracker, state_machine
    if detector is None:
        detector = YOLODetector()
        tracker = SimpleTracker(max_age=30, min_hits=3, iou_threshold=0.3)
        state_machine = StateMachine()


@router.post("/start")
async def start_monitoring():
    """启动监控"""
    global detector, tracker, state_machine

    init_components()
    zone_manager.reload()

    config = config_manager.get_config()

    # 为每个启用的摄像头启动流
    for camera in config.cameras:
        if camera.enabled:

            def frame_callback(frame, camera_id=camera.id):
                process_frame(frame, camera_id)

            stream = stream_manager.add_stream(camera.id, camera.source, frame_callback)
            stream.start()

    return {"message": "Monitoring started", "cameras": len(config.cameras)}


@router.post("/stop")
async def stop_monitoring():
    """停止监控"""
    stream_manager.stop_all()
    return {"message": "Monitoring stopped"}


@router.get("/status")
async def get_status():
    """获取监控状态"""
    return {
        "streams": stream_manager.get_status(),
        "redis": redis_client.get_system_status(),
    }


def process_frame(frame: np.ndarray, camera_id: str):
    """处理单帧"""
    global detector, tracker, state_machine

    if detector is None or tracker is None or state_machine is None:
        return

    try:
        # 1. 检测person_carry
        detections = detector.detect(frame)

        # 2. 更新追踪器，获取稳定的track_id
        tracks = tracker.update(detections)

        # 3. 准备违规规则
        config = config_manager.get_config()
        violation_rules = [
            {
                "from_zone": rule.from_zone,
                "to_zone": rule.to_zone,
                "name": rule.name,
            }
            for rule in config.violation_rules
            if rule.enabled
        ]

        frame_height, frame_width = frame.shape[:2]

        # 4. 更新状态机并检查违规
        for track in tracks:
            # 确定当前区域（根据实际帧尺寸缩放区域坐标）
            current_zone = zone_manager.get_zone_id_at_point_scaled(
                track.center, frame_width, frame_height
            )

            # 更新状态机
            if track.hits == 1:
                # 新轨迹
                state_machine.start_tracking(track.id, current_zone)

            state_machine.update_position(track.id, track.center, current_zone)

            # 检查违规
            violation = state_machine.check_violation(track.id, violation_rules)
            if violation:
                # 发送RabbitMQ消息
                _send_violation_alert(violation, camera_id)

                # 重置该轨迹（避免重复报警）
                state_machine.reset_track(track.id)

        # 5. 清理过期轨迹
        stale_tracks = state_machine.cleanup_stale_tracks(timeout_seconds=30)
        if stale_tracks:
            print(f"[Monitor] 清理过期轨迹: {stale_tracks}")

    except Exception as e:
        print(f"[ProcessFrame] Error: {e}")


def _send_violation_alert(violation: dict, camera_id: str):
    """发送违规警报到RabbitMQ"""
    message = {
        "type": "violation",
        "camera_id": camera_id,
        "track_id": violation["track_id"],
        "rule_name": violation["rule_name"],
        "from_zone": violation["from_zone"],
        "to_zone": violation["to_zone"],
        "timestamp": violation["timestamp"],
        "trajectory_summary": violation["trajectory"][-10:]
        if violation["trajectory"]
        else [],
    }

    try:
        rabbitmq_client.publish_violation(message)
        print(f"[Monitor] 违规警报已发送: {violation['rule_name']}")
    except Exception as e:
        print(f"[Monitor] 发送违规警报失败: {e}")


@router.get("/test-frame")
async def test_frame(camera_id: str = "test"):
    """测试单帧处理"""
    init_components()

    # 创建测试帧
    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

    # 处理
    detections = detector.detect(frame)
    tracks = tracker.update(detections)

    return {
        "detections": len(detections),
        "tracks": len(tracks),
        "camera_id": camera_id,
    }


@router.get("/camera-frame")
async def get_camera_frame(camera_id: str):
    """获取摄像头/视频的第一帧"""
    config = config_manager.get_config()

    # 查找摄像头配置
    camera = None
    for cam in config.cameras:
        if cam.id == camera_id:
            camera = cam
            break

    if not camera:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")

    try:
        # 尝试打开视频源
        cap = cv2.VideoCapture(camera.source)

        if not cap.isOpened():
            raise HTTPException(
                status_code=400, detail=f"Cannot open video source: {camera.source}"
            )

        # 读取第一帧
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            raise HTTPException(
                status_code=400, detail="Failed to capture frame from video source"
            )

        # OpenCV读取视频帧为BGR格式
        # 浏览器期望RGB格式显示
        # 由于cv2.imencode默认按BGR处理，我们需要:
        # 1. BGR -> RGB (让内存中的数据为RGB)
        # 2. RGB -> BGR (欺骗OpenCV，让它以为数据是BGR，实际编码后就是RGB)
        # 这样浏览器看到的就是正确的RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_for_encode = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

        # 编码为JPEG（添加质量参数）
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, 95]
        _, buffer = cv2.imencode(".jpg", frame_for_encode, encode_params)
        img_base64 = base64.b64encode(buffer).decode("utf-8")

        return {
            "camera_id": camera_id,
            "image": f"data:image/jpeg;base64,{img_base64}",
            "width": frame.shape[1],
            "height": frame.shape[0],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error capturing frame: {str(e)}")


@router.post("/debug-process")
async def debug_process_video(video_path: str, frame_number: int = 0):
    """
    调试接口：处理视频文件的指定帧并返回带标注的图像
    """
    try:
        processed_frame, detection_info = process_video_frame_debug(
            video_path=video_path,
            frame_number=frame_number,
            camera_id="debug",
        )

        if processed_frame is None:
            raise HTTPException(
                status_code=400,
                detail=detection_info.get("error", "处理视频时发生错误"),
            )

        frame_rgb = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB)
        frame_for_encode = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

        encode_params = [cv2.IMWRITE_JPEG_QUALITY, 90]
        _, buffer = cv2.imencode(".jpg", frame_for_encode, encode_params)
        img_base64 = base64.b64encode(buffer).decode("utf-8")

        return {
            "success": True,
            "image": f"data:image/jpeg;base64,{img_base64}",
            "width": processed_frame.shape[1],
            "height": processed_frame.shape[0],
            "detection_info": detection_info,
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        print(f"[DebugProcess] Error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"处理视频时发生错误: {str(e)}")


@router.get("/debug-video-info")
async def get_video_info(video_path: str):
    """
    获取视频文件信息
    """
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise HTTPException(
                status_code=400, detail=f"无法打开视频文件: {video_path}"
            )

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        info = {
            "path": video_path,
            "total_frames": total_frames,
            "fps": fps,
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "duration": int(total_frames) / fps if fps > 0 else 0,
        }
        cap.release()

        return info

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取视频信息失败: {str(e)}")
