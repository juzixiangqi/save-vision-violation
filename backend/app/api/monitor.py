from fastapi import APIRouter, HTTPException
from typing import Dict, List
from app.services.video_stream import stream_manager
from app.services.redis_client import redis_client
from app.services.rabbitmq_client import rabbitmq_client
from app.config.manager import config_manager
from app.core.detector import YOLODetector
from app.core.violation_checker import ViolationChecker
from app.core.zone_manager import zone_manager
import cv2
import numpy as np

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
        # 检测人员和姿态
        persons, poses = detector.detect(frame)

        # 检测箱子（暂时为空，需要自定义实现）
        boxes = []

        # 检查违规
        violations = violation_checker.process_frame(persons, poses, boxes, camera_id)

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
    persons, poses = detector.detect(frame)

    return {
        "persons_detected": len(persons),
        "poses_detected": len(poses),
        "camera_id": camera_id,
    }
