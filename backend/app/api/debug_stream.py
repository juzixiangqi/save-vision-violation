import asyncio
import cv2
import numpy as np
import base64
import json
from typing import Dict, Optional, Set
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from app.core.detector import YOLODetector, Detection, Pose
from app.core.tracker import SimpleTracker
from app.core.state_machine import StateMachine
from app.core.zone_manager import zone_manager
from app.core.debug_visualizer import DebugVisualizer
from app.config.manager import config_manager
from app.services.rabbitmq_client import rabbitmq_client

# 创建线程池用于执行同步的 YOLO 检测
detector_executor = ThreadPoolExecutor(max_workers=1)

router = APIRouter(prefix="/api/monitor", tags=["debug-stream"])

# 活跃流跟踪
active_streams: Dict[str, bool] = {}


class StreamRequest(BaseModel):
    video_path: str
    camera_id: str = "debug"
    frame_skip: int = 0
    speed: float = 1.0


def track_to_pose(track) -> Pose:
    """将 Track 转换为 Pose（兼容性转换）"""
    return Pose(
        id=track.id,
        bbox=track.bbox,
        confidence=0.9,
        keypoints=np.zeros((17, 3), dtype=np.float32),  # 空的关键点
    )


def process_frame_sync(
    frame: np.ndarray,
    detector: YOLODetector,
    tracker: SimpleTracker,
    state_machine: StateMachine,
    visualizer: DebugVisualizer,
    camera_id: str,
    frame_number: int,
    total_frames: int,
) -> tuple:
    """同步处理单帧（在线程池中运行）- 适配新的检测逻辑"""
    # 1. 检测 person_carry
    detections = detector.detect(frame)

    # 2. 更新追踪器，获取稳定的 track_id
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

    # 4. 计算区域并更新状态机
    frame_height, frame_width = frame.shape[:2]
    violations = []
    track_zones = {}

    for track in tracks:
        raw_zone = zone_manager.get_zone_id_at_point_scaled(
            track.bottom_center, frame_width, frame_height
        )

        # 空白区域保持：如果当前无区域但状态机中记录过上一个区域，显式回退
        track_data = state_machine.get_track(track.id)
        effective_zone = raw_zone
        if effective_zone is None and track_data is not None:
            effective_zone = track_data.last_known_zone or track_data.current_zone
            print(
                f"[DebugStream.process_frame_sync] track={track.id} raw_zone=None -> "
                f"effective_zone={effective_zone}"
            )
        else:
            print(
                f"[DebugStream.process_frame_sync] track={track.id} raw_zone={raw_zone} "
                f"hits={track.hits}"
            )

        if track.hits == 1:
            print(
                f"[DebugStream.process_frame_sync] track={track.id} 新轨迹，start_tracking"
            )
            state_machine.start_tracking(track.id, effective_zone)
        elif track_data is None:
            print(
                f"[DebugStream.process_frame_sync] track={track.id} tracker存在但状态机无数据，"
                f"重新start_tracking"
            )
            state_machine.start_tracking(track.id, effective_zone)

        state_machine.update_position(track.id, track.bottom_center, effective_zone)

        # 获取状态机处理后的区域（含防抖和空白区域保持）
        track_data = state_machine.get_track(track.id)
        track_zones[track.id] = track_data.current_zone if track_data else raw_zone

        # 检查违规
        violation = state_machine.check_violation(track.id, violation_rules)
        if violation:
            violations.append(violation)
            state_machine.reset_track(track.id)

    # 5. 转换为 Pose 列表以兼容 visualizer
    poses = [track_to_pose(track) for track in tracks]

    # 6. 绘制标注
    frame_info = f"帧号: {frame_number}/{total_frames}"
    processed_frame = visualizer.draw_detections(
        frame,
        poses,
        [],  # boxes 为空列表
        violations,
        camera_id,
        frame_info,
        state_machine=state_machine,
    )

    return processed_frame, poses, [], violations, track_zones


async def process_video_stream(
    video_path: str, camera_id: str, frame_skip: int, speed: float, stream_id: str
):
    """处理视频流并生成 SSE 事件"""
    global active_streams

    # 打开视频
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        yield f"event: error\ndata: {json.dumps({'message': f'无法打开视频: {video_path}'})}\n\n"
        return

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_delay = 1.0 / fps if fps > 0 else 0.033

    # 初始化组件 - 使用全局单例保持跟踪状态
    detector = get_detector()
    tracker = get_tracker()
    state_machine = get_state_machine()
    visualizer = DebugVisualizer(
        frame_width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        frame_height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
    )

    # 重置区域管理器
    zone_manager.reload()

    frame_number = 0
    last_yield_time = asyncio.get_event_loop().time()

    try:
        while active_streams.get(stream_id, False):
            ret, frame = cap.read()
            if not ret:
                # 视频结束
                yield f"event: end\ndata: {json.dumps({'type': 'end', 'message': '视频播放完成'})}\n\n"
                break

            frame_number += 1

            # 跳帧处理
            if frame_skip > 0 and frame_number % (frame_skip + 1) != 0:
                continue

            # 使用线程池执行同步的 YOLO 检测，避免阻塞事件循环
            loop = asyncio.get_event_loop()
            (
                processed_frame,
                poses,
                boxes,
                violations,
                track_zones,
            ) = await loop.run_in_executor(
                detector_executor,
                process_frame_sync,
                frame,
                detector,
                tracker,
                state_machine,
                visualizer,
                camera_id,
                frame_number,
                total_frames,
            )

            # 编码为 base64
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, 75]
            _, buffer = cv2.imencode(".jpg", processed_frame, encode_params)
            img_base64 = base64.b64encode(buffer).decode("utf-8")

            # 构建帧数据
            frame_data = {
                "type": "frame",
                "timestamp": datetime.now().isoformat(),
                "frame_number": frame_number,
                "total_frames": total_frames,
                "fps": round(fps * speed, 1),
                "image": f"data:image/jpeg;base64,{img_base64}",
                "width": processed_frame.shape[1],
                "height": processed_frame.shape[0],
                "detections": {
                    "persons": len(poses),
                    "poses": len(poses),
                    "violations": violations,
                    "track_zones": track_zones,
                },
            }

            yield f"event: frame\ndata: {json.dumps(frame_data)}\n\n"

            # 发送违规事件
            for violation in violations:
                violation_data = {
                    "timestamp": datetime.now().isoformat(),
                    "frame_number": frame_number,
                    "data": violation,
                }
                yield f"event: violation\ndata: {json.dumps(violation_data)}\n\n"

            # 控制帧率 - 使用自适应延迟
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - last_yield_time
            target_delay = frame_delay / speed
            sleep_time = max(0, target_delay - elapsed)

            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

            last_yield_time = asyncio.get_event_loop().time()

    except Exception as e:
        error_data = {"type": "error", "message": str(e)}
        yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
    finally:
        cap.release()
        if stream_id in active_streams:
            del active_streams[stream_id]


@router.post("/debug-stream")
async def start_debug_stream(request: StreamRequest):
    """启动视频调试流"""
    import uuid

    stream_id = str(uuid.uuid4())
    active_streams[stream_id] = True

    return StreamingResponse(
        process_video_stream(
            video_path=request.video_path,
            camera_id=request.camera_id,
            frame_skip=request.frame_skip,
            speed=request.speed,
            stream_id=stream_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Stream-Id": stream_id,
        },
    )


@router.post("/debug-stream/stop")
async def stop_debug_stream(request: dict):
    """停止视频调试流"""
    stream_id = request.get("stream_id")
    if not stream_id:
        raise HTTPException(status_code=400, detail="缺少 stream_id 参数")

    if stream_id in active_streams:
        active_streams[stream_id] = False
        return {"message": "流已停止", "stream_id": stream_id}
    else:
        raise HTTPException(status_code=404, detail="流不存在或已停止")


@router.get("/debug-stream/status")
async def get_stream_status():
    """获取活跃流状态"""
    return {"active_streams": list(active_streams.keys()), "count": len(active_streams)}


# ============ 简单图片帧端点（用于测试）============

from fastapi import File, UploadFile

# 全局组件实例（避免每次请求都重新加载模型）
_detector: Optional[YOLODetector] = None
_tracker: Optional[SimpleTracker] = None
_state_machine: Optional[StateMachine] = None


def get_detector() -> YOLODetector:
    global _detector
    if _detector is None:
        _detector = YOLODetector()
    return _detector


def get_tracker() -> SimpleTracker:
    global _tracker
    if _tracker is None:
        _tracker = SimpleTracker(
            max_age=30, min_hits=3, iou_threshold=0.3, distance_threshold=400.0
        )
    return _tracker


def get_state_machine() -> StateMachine:
    global _state_machine
    if _state_machine is None:
        _state_machine = StateMachine()
    return _state_machine


@router.post("/debug-frame")
async def process_frame_debug(
    file: UploadFile = File(...),
    camera_id: str = "debug",
    draw_boxes: bool = True,
    draw_poses: bool = True,
    draw_zones: bool = True,
):
    """
    处理单帧图片并返回带标注的结果 - 适配新的检测逻辑
    
    使用方式:
    curl -X POST "http://localhost:8000/api/monitor/debug-frame" \
         -F "file=@your_image.jpg" \
         -F "camera_id=cam1"
    
    或者使用前端FormData上传
    """
    try:
        # 读取上传的图片
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            raise HTTPException(status_code=400, detail="无法读取图片文件")

        # 初始化组件
        detector = get_detector()
        tracker = get_tracker()
        state_machine = get_state_machine()
        visualizer = DebugVisualizer(
            frame_width=frame.shape[1],
            frame_height=frame.shape[0],
        )

        # 刷新区域配置
        zone_manager.reload()

        # 使用线程池执行检测（避免阻塞）
        loop = asyncio.get_event_loop()

        def do_detection():
            # 1. 检测 person_carry
            detections = detector.detect(frame)

            # 2. 更新追踪器
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

            # 4. 计算区域并更新状态机
            frame_height, frame_width = frame.shape[:2]
            violations = []
            track_zones = {}

            for track in tracks:
                raw_zone = zone_manager.get_zone_id_at_point_scaled(
                    track.bottom_center, frame_width, frame_height
                )
                print(
                    f"[DebugStream.debug-frame] track={track.id} raw_zone={raw_zone} "
                    f"hits={track.hits} (注意：此端点暂未使用effective_zone回退)"
                )

                if track.hits == 1:
                    print(
                        f"[DebugStream.debug-frame] track={track.id} 新轨迹，start_tracking"
                    )
                    state_machine.start_tracking(track.id, raw_zone)

                state_machine.update_position(track.id, track.bottom_center, raw_zone)

                # 获取状态机处理后的区域（含防抖和空白区域保持）
                track_data = state_machine.get_track(track.id)
                track_zones[track.id] = (
                    track_data.current_zone if track_data else raw_zone
                )

                violation = state_machine.check_violation(track.id, violation_rules)
                if violation:
                    violations.append(violation)
                    state_machine.reset_track(track.id)

            # 5. 转换为 Pose 列表
            poses = [track_to_pose(track) for track in tracks]

            return poses, violations, track_zones

        poses, violations, track_zones = await loop.run_in_executor(
            detector_executor, do_detection
        )

        # 绘制标注
        processed_frame = visualizer.draw_detections(
            frame,
            poses,
            [],  # boxes
            violations,
            camera_id,
            "",
            state_machine=state_machine,
        )

        # 编码为JPEG
        _, buffer = cv2.imencode(".jpg", processed_frame)
        img_base64 = base64.b64encode(buffer).decode("utf-8")

        # 构建响应
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "camera_id": camera_id,
            "image": f"data:image/jpeg;base64,{img_base64}",
            "width": frame.shape[1],
            "height": frame.shape[0],
            "detections": {
                "persons": len(poses),
                "boxes": 0,
                "poses": len(poses),
                "violations": violations,
                "track_zones": track_zones,
            },
            "person_details": [
                {
                    "id": p.id,
                    "bbox": p.bbox,
                    "confidence": p.confidence,
                    "zone": track_zones.get(p.id),
                }
                for p in poses
            ],
            "box_details": [],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理图片时出错: {str(e)}")


@router.get("/debug-frame/test")
async def test_frame_endpoint():
    """测试图片帧端点是否可用"""
    detector = get_detector()

    config = detector.detection_params

    return {
        "status": "ok",
        "message": "图片帧端点正常运行",
        "model_info": {
            "type": "person_carry",
            "model_path": config.person_carry.model,
            "confidence": config.person_carry.confidence,
            "iou_threshold": config.person_carry.iou_threshold,
            "class_id": config.person_carry.class_id,
        },
        "usage": {
            "endpoint": "POST /api/monitor/debug-frame",
            "method": "使用 multipart/form-data 上传图片",
            "example": 'curl -X POST "http://localhost:8000/api/monitor/debug-frame" -F "file=@image.jpg"',
        },
    }


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
        print(f"[DebugStream] 违规警报已发送: {violation['rule_name']}")
    except Exception as e:
        print(f"[DebugStream] 发送违规警报失败: {e}")
