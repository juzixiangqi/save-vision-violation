from fastapi import APIRouter, HTTPException
from typing import Dict, List
from app.services.video_stream import stream_manager
from app.services.redis_client import redis_client
from app.services.rabbitmq_client import rabbitmq_client
from app.config.manager import config_manager
from app.core.detector import YOLODetector
from app.core.violation_checker import ViolationChecker
from app.core.zone_manager import zone_manager
from app.core.debug_visualizer import process_video_frame_debug
import cv2
import numpy as np
import base64
from io import BytesIO

router = APIRouter(prefix="/api/monitor", tags=["monitor"])

# 全局检测器和违规检查器
detector: YOLODetector = None
violation_checker: ViolationChecker = None


def init_detector():
    """初始化检测器"""
    global detector, violation_checker
    if detector is None:
        detector = YOLODetector()
        violation_checker = ViolationChecker()


@router.post("/start")
async def start_monitoring():
    """启动监控"""
    global detector, violation_checker

    init_detector()
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
    global detector, violation_checker

    if detector is None or violation_checker is None:
        return

    try:
        # 检测人员姿态
        poses = detector.detect(frame)

        # 检测箱子
        boxes = detector.detect_boxes(frame)

        # 检查违规（使用poses替代persons）
        violations = violation_checker.process_frame(
            poses, boxes, camera_id, frame=frame
        )

        # 发送违规告警
        for violation in violations:
            rabbitmq_client.publish_violation(violation)

    except Exception as e:
        print(f"[ProcessFrame] Error: {e}")


@router.get("/test-frame")
async def test_frame(camera_id: str = "test"):
    """测试单帧处理"""
    init_detector()

    # 创建测试帧
    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

    # 处理
    poses = detector.detect(frame)

    return {
        "persons_detected": len(poses),
        "poses_detected": len(poses),
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

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error capturing frame: {str(e)}")


@router.post("/debug-process")
async def debug_process_video(video_path: str, frame_number: int = 0):
    """
    调试接口：处理视频文件的指定帧并返回带标注的图像

    Args:
        video_path: 视频文件路径
        frame_number: 要处理的帧号（从0开始）

    Returns:
        包含处理后图像和检测信息的JSON
    """
    try:
        # 处理视频帧
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

        # 将处理后的帧编码为base64
        # BGR -> RGB -> BGR 转换确保浏览器显示正确
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

    Args:
        video_path: 视频文件路径

    Returns:
        视频信息（总帧数、FPS、分辨率等）
    """
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise HTTPException(
                status_code=400, detail=f"无法打开视频文件: {video_path}"
            )

        info = {
            "path": video_path,
            "total_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            "fps": cap.get(cv2.CAP_PROP_FPS),
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "duration": int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            / cap.get(cv2.CAP_PROP_FPS)
            if cap.get(cv2.CAP_PROP_FPS) > 0
            else 0,
        }
        cap.release()

        return info

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取视频信息失败: {str(e)}")
