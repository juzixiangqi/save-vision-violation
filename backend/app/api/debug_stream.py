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

from app.core.detector import YOLODetector
from app.core.violation_checker import ViolationChecker
from app.core.zone_manager import zone_manager
from app.core.debug_visualizer import DebugVisualizer

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


def process_frame_sync(
    frame: np.ndarray,
    detector: YOLODetector,
    checker: ViolationChecker,
    visualizer: DebugVisualizer,
    camera_id: str,
    frame_number: int,
    total_frames: int,
) -> tuple:
    """同步处理单帧（在线程池中运行）"""
    # 处理帧
    persons, poses = detector.detect(frame)
    boxes = []  # TODO: 箱子检测
    violations = checker.process_frame(persons, poses, boxes, camera_id)

    # 绘制标注
    frame_info = f"帧号: {frame_number}/{total_frames}"
    processed_frame = visualizer.draw_detections(
        frame, persons, poses, boxes, violations, camera_id, frame_info
    )

    return processed_frame, persons, poses, violations


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

    # 初始化组件
    detector = YOLODetector()
    checker = ViolationChecker()
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
            processed_frame, persons, poses, violations = await loop.run_in_executor(
                detector_executor,
                process_frame_sync,
                frame,
                detector,
                checker,
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
                    "persons": len(persons),
                    "poses": len(poses),
                    "violations": violations,
                },
            }

            yield f"event: frame\ndata: {json.dumps(frame_data)}\n\n"

            # 发送违规事件
            for violation in violations:
                violation_data = {
                    "type": "violation",
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
