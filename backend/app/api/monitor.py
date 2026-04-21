from fastapi import APIRouter, HTTPException
from typing import Dict, List, Optional
from app.services.video_stream import stream_manager
from app.services.redis_client import redis_client
from app.services.rabbitmq_client import rabbitmq_client
from app.services.rtsp_client import rtsp_client
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
        tracker = SimpleTracker(
            max_age=30, min_hits=3, iou_threshold=0.3, distance_threshold=400.0
        )
        state_machine = StateMachine()


@router.post("/start")
async def start_monitoring():
    """启动监控"""
    global detector, tracker, state_machine

    init_components()
    zone_manager.reload()

    config = config_manager.get_config()

    # 为每个启用的摄像头启动流
    started_cameras = []
    for camera in config.cameras:
        if camera.enabled:
            source = camera.source
            # 如果配置了camera_code，通过API获取RTSP流地址
            if camera.camera_code:
                rtsp_url = rtsp_client.get_stream_url(camera.camera_code)
                if rtsp_url:
                    source = rtsp_url
                    print(
                        f"[Monitor] Camera {camera.id}({camera.name}) RTSP resolved: {source}"
                    )
                else:
                    print(
                        f"[Monitor] Camera {camera.id}({camera.name}) failed to resolve RTSP, using source: {source}"
                    )

            def frame_callback(frame, camera_id=camera.id):
                process_frame(frame, camera_id)

            stream = stream_manager.add_stream(
                camera.id, source, frame_callback, detection_interval=5
            )
            stream.start()
            started_cameras.append(camera.id)

    return {
        "message": "Monitoring started",
        "cameras": len(started_cameras),
        "started": started_cameras,
    }


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
        tracks_to_reset = []
        for track in tracks:
            # 确定当前区域（使用检测框底部中点，根据实际帧尺寸缩放区域坐标）
            raw_zone = zone_manager.get_zone_id_at_point_scaled(
                track.bottom_center, frame_width, frame_height
            )

            # 空白区域保持：如果当前无区域但状态机中记录过上一个区域，显式回退
            track_data = state_machine.get_track(track.id)
            effective_zone = raw_zone
            if effective_zone is None and track_data is not None:
                effective_zone = track_data.last_known_zone or track_data.current_zone
                print(
                    f"[Monitor.process_frame] track={track.id} raw_zone=None -> "
                    f"effective_zone={effective_zone} (last_known={track_data.last_known_zone}, "
                    f"current={track_data.current_zone})"
                )
            else:
                print(
                    f"[Monitor.process_frame] track={track.id} raw_zone={raw_zone} "
                    f"hits={track.hits} age={track.age}"
                )

            # 更新状态机
            if track.hits == 1:
                # 新轨迹
                print(
                    f"[Monitor.process_frame] track={track.id} 新轨迹，start_tracking"
                )
                state_machine.start_tracking(track.id, effective_zone)
            elif track_data is None:
                # tracker 还在追踪但状态机中被 reset 了，以当前有效区域重新注册
                print(
                    f"[Monitor.process_frame] track={track.id} tracker存在但状态机无数据，"
                    f"重新start_tracking"
                )
                state_machine.start_tracking(track.id, effective_zone)

            state_machine.update_position(track.id, track.bottom_center, effective_zone)

            # 检查违规（先收集，延迟到本帧处理完再 reset）
            violation = state_machine.check_violation(track.id, violation_rules)
            if violation:
                # 发送RabbitMQ消息
                camera_name = ""
                config = config_manager.get_config()
                for cam in config.cameras:
                    if cam.id == camera_id:
                        camera_name = cam.name
                        break
                _send_violation_alert(violation, camera_id, camera_name)
                tracks_to_reset.append(track.id)

        # 重置违规轨迹（避免重复报警）
        for track_id in tracks_to_reset:
            state_machine.reset_track(track_id)

        # 5. 清理过期轨迹
        stale_tracks = state_machine.cleanup_stale_tracks(timeout_seconds=30)
        if stale_tracks:
            print(f"[Monitor] 清理过期轨迹: {stale_tracks}")

    except Exception as e:
        print(f"[ProcessFrame] Error: {e}")


def _send_violation_alert(violation: dict, camera_id: str, camera_name: str = ""):
    """发送违规警报到RabbitMQ"""
    from datetime import datetime

    now = datetime.now()
    message = {
        "camera_name": camera_name or camera_id,
        "model_name": "box",
        "start_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": now.strftime("%Y-%m-%d %H:%M:%S"),
    }

    try:
        rabbitmq_client.publish_violation(message)
        print(
            f"[Monitor] 违规警报已发送: {violation.get('track_id')} "
            f"{violation.get('from_zone')} -> {violation.get('to_zone')}"
        )
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
