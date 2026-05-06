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
from app.core.async_detector import AsyncDetector
import cv2
import numpy as np
import base64
import os
from io import BytesIO
import threading
import subprocess
import shutil
import platform

# Windows 上强制 OpenCV 的 FFmpeg 后端使用 TCP 传输 RTSP
# 解决 Windows 防火墙/网络策略对 UDP 的限制
if platform.system() == "Windows":
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

router = APIRouter(prefix="/api/monitor", tags=["monitor"])

# 全局组件
detector: YOLODetector = None
async_detector: AsyncDetector = None
tracker: SimpleTracker = None
state_machine: StateMachine = None


def init_components():
    """初始化检测组件"""
    global detector, async_detector, tracker, state_machine
    if detector is None:
        detector = YOLODetector()
        # 创建异步检测器（只负责超时保护，不做节流）
        # 检测频率由 VideoStream.detection_interval 统一控制
        async_config = detector.detection_params.async_detection
        print(
            f"[Monitor] AsyncDetector config: api_timeout={async_config.api_timeout}, max_pending={async_config.max_pending}"
        )
        async_detector = AsyncDetector(
            detector=detector,
            api_timeout=async_config.api_timeout,
            max_pending=async_config.max_pending,
        )
        tracker = SimpleTracker(
            max_age=30, min_hits=3, iou_threshold=0.3, distance_threshold=400.0
        )
        state_machine = StateMachine()


@router.post("/start")
async def start_monitoring():
    """启动监控"""
    global detector, async_detector, tracker, state_machine

    init_components()
    zone_manager.reload()

    config = config_manager.get_config()

    # 为每个启用的摄像头启动流
    started_cameras = []
    for camera in config.cameras:
        if camera.enabled:
            source = camera.source
            # 如果配置了海康威视配置，使用保存的凭据重新获取时效性RTSP流地址
            if camera.hikvision_config:
                config_dict = camera.hikvision_config.model_dump()
                rtsp_url = rtsp_client.get_stream_url(
                    camera.hikvision_config.cameraIndexCode,
                    config=config_dict
                )
                if rtsp_url:
                    source = rtsp_url
                    camera.source = rtsp_url
                    config_manager.update_config(config)
                    print(
                        f"[Monitor] Camera {camera.id}({camera.name}) RTSP resolved via hikvision_config: {source}"
                    )
                else:
                    print(
                        f"[Monitor] Camera {camera.id}({camera.name}) failed to resolve RTSP via hikvision_config, using source: {source}"
                    )
            # 向后兼容：旧配置只有 camera_code
            elif camera.camera_code:
                rtsp_url = rtsp_client.get_stream_url(camera.camera_code)
                if rtsp_url:
                    source = rtsp_url
                    camera.source = rtsp_url
                    config_manager.update_config(config)
                    print(
                        f"[Monitor] Camera {camera.id}({camera.name}) RTSP resolved via camera_code: {source}"
                    )
                else:
                    print(
                        f"[Monitor] Camera {camera.id}({camera.name}) failed to resolve RTSP, using source: {source}"
                    )

            def frame_callback(frame, camera_id=camera.id):
                process_frame(frame, camera_id)

            # 使用异步回调模式
            # detection_interval=6: 每6帧检测一次，由 VideoStream 统一控制频率
            # AsyncDetector 只负责 API 超时保护，不做额外节流
            stream = stream_manager.add_stream(
                camera.id,
                source,
                frame_callback,
                detection_interval=6,
                async_callback=True,
            )
            stream.start()
            started_cameras.append(camera.id)

    return {
        "message": "Monitoring started",
        "cameras": len(started_cameras),
        "started": started_cameras,
        "async_detector": {
            "detection_interval": 6,
            "api_timeout": async_detector.api_timeout if async_detector else 0.25,
        },
    }


@router.post("/stop")
async def stop_monitoring():
    """停止监控"""
    stream_manager.stop_all()
    return {"message": "Monitoring stopped"}


@router.get("/status")
async def get_status():
    """获取监控状态"""
    status = {
        "streams": stream_manager.get_status(),
        "redis": redis_client.get_system_status(),
    }

    # 添加异步检测器统计
    if async_detector:
        status["async_detector"] = async_detector.get_stats()

    return status


def process_frame(frame: np.ndarray, camera_id: str):
    """处理单帧 - 使用异步检测"""
    global async_detector, tracker, state_machine

    if async_detector is None or tracker is None or state_machine is None:
        return

    try:
        # 1. 异步检测（每6帧实际调用一次API，超时使用缓存结果）
        detections = async_detector.on_frame(frame, camera_id)

        # 如果还没有结果（首次运行），跳过处理
        if detections is None:
            return

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
                _send_violation_alert(violation, camera_id, camera_name or camera_id)
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


def _try_capture_with_ffmpeg(source: str, camera_id: str, timeout_ms: int = 5000) -> tuple:
    """使用 ffmpeg 命令行捕获视频帧
    
    在 Windows 上 OpenCV 的 VideoCapture 可能无法正确打开 RTSP 流，
    ffmpeg 命令行更可靠。使用 subprocess 调用 ffmpeg。
    
    Args:
        source: 视频源地址
        camera_id: 摄像头ID（用于日志）
        timeout_ms: 超时时间（毫秒），默认5秒
    
    Returns:
        (success: bool, result: dict or str)
    """
    # 检查 ffmpeg 是否可用（先检查常见路径）
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        # 检查常见安装路径
        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
            r"C:\Users\%USERNAME%\ffmpeg\bin\ffmpeg.exe",
            r"C:\tools\ffmpeg\bin\ffmpeg.exe",
        ]
        for p in common_paths:
            expanded = os.path.expandvars(p)
            if os.path.isfile(expanded):
                ffmpeg_path = expanded
                print(f"[CameraFrame] Found ffmpeg at: {ffmpeg_path}")
                break
    
    if not ffmpeg_path:
        print(f"[CameraFrame] ffmpeg not found in PATH. Current PATH: {os.environ.get('PATH', '')[:500]}")
        return False, "ffmpeg 未安装或未在 PATH 中"
    
    print(f"[CameraFrame] Trying ffmpeg fallback for: {source}")
    
    # 构建 ffmpeg 命令
    # -rtsp_transport tcp: 使用 TCP 传输（Windows 上 UDP 可能有问题）
    # -ss 00:00:01: 跳到 1 秒处（跳过初始缓冲）
    # -vframes 1: 只取 1 帧
    # -f image2pipe: 输出到管道
    # -vcodec mjpeg: MJPEG 编码
    cmd = [
        ffmpeg_path,
        "-rtsp_transport", "tcp",
        "-i", source,
        "-vframes", "1",
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "-q:v", "2",
        "-"
    ]
    
    try:
        # 执行 ffmpeg，捕获 stdout
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_ms / 1000.0,
        )
        
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="ignore")[:500]
            print(f"[CameraFrame] ffmpeg failed: {stderr}")
            return False, f"ffmpeg 执行失败: {stderr}"
        
        # 从 stdout 读取图像数据
        image_data = result.stdout
        if not image_data or len(image_data) < 100:
            return False, "ffmpeg 未返回有效图像数据"
        
        # 使用 OpenCV 解码图像以获取尺寸
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return False, "无法解码 ffmpeg 返回的图像"
        
        # 编码为 base64
        _, buffer = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        img_base64 = base64.b64encode(buffer).decode("utf-8")
        
        print(f"[CameraFrame] ffmpeg success: {img.shape[1]}x{img.shape[0]}")
        return True, {
            "image": f"data:image/jpeg;base64,{img_base64}",
            "width": img.shape[1],
            "height": img.shape[0],
        }
        
    except subprocess.TimeoutExpired:
        print(f"[CameraFrame] ffmpeg timed out after {timeout_ms}ms")
        return False, f"ffmpeg 超时（{timeout_ms}ms）"
    except Exception as e:
        print(f"[CameraFrame] ffmpeg exception: {e}")
        return False, f"ffmpeg 异常: {str(e)}"


def _try_capture_frame(source: str, camera_id: str, timeout_ms: int = 5000) -> tuple:
    """尝试打开视频源并捕获第一帧（优先使用 ffmpeg，fallback 到 OpenCV）
    
    策略：
    1. 优先使用 ffmpeg 命令行（在 Windows 上更可靠，避免 OpenCV 长时间 hang 住）
    2. 如果 ffmpeg 不可用或失败，fallback 到 OpenCV VideoCapture
    
    Args:
        source: 视频源地址
        camera_id: 摄像头ID（用于日志）
        timeout_ms: 超时时间（毫秒），默认5秒
    
    Returns:
        (success: bool, result: dict or str)
        成功时返回 (True, {"image": base64_str, "width": int, "height": int})
        失败时返回 (False, error_message)
    """
    print(f"[CameraFrame] Trying to open source: {source} (timeout={timeout_ms}ms)")
    
    # 步骤1：优先使用 ffmpeg（在 Windows 上更可靠）
    print(f"[CameraFrame] Camera {camera_id} trying ffmpeg first...")
    success, result = _try_capture_with_ffmpeg(source, camera_id, timeout_ms=timeout_ms)
    if success:
        return True, result
    
    print(f"[CameraFrame] Camera {camera_id} ffmpeg failed: {result}, trying OpenCV fallback...")
    
    # 步骤2：fallback 到 OpenCV
    capture_result = {"success": False, "result": None, "done": False}
    
    def _capture_worker():
        try:
            # Windows 上强制使用 TCP 传输
            if platform.system() == "Windows":
                os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
            
            cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
            
            if not cap.isOpened():
                capture_result["result"] = f"Cannot open video source: {source}"
                capture_result["done"] = True
                return
            
            # 读取第一帧
            ret, frame = cap.read()
            cap.release()
            
            if not ret or frame is None:
                capture_result["result"] = "Failed to capture frame from video source"
                capture_result["done"] = True
                return
            
            # 编码为JPEG
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, 95]
            _, buffer = cv2.imencode(".jpg", frame, encode_params)
            img_base64 = base64.b64encode(buffer).decode("utf-8")
            
            capture_result["success"] = True
            capture_result["result"] = {
                "image": f"data:image/jpeg;base64,{img_base64}",
                "width": frame.shape[1],
                "height": frame.shape[0],
            }
            capture_result["done"] = True
        except Exception as e:
            capture_result["result"] = f"Exception during capture: {str(e)}"
            capture_result["done"] = True
    
    # 启动工作线程
    worker = threading.Thread(target=_capture_worker)
    worker.daemon = True
    worker.start()
    
    # 等待超时
    worker.join(timeout=timeout_ms / 1000.0)
    
    if worker.is_alive():
        print(f"[CameraFrame] Camera {camera_id} OpenCV timed out after {timeout_ms}ms")
        return False, f"OpenCV 超时（{timeout_ms}ms）"
    
    if capture_result["done"]:
        if capture_result["success"]:
            return capture_result["success"], capture_result["result"]
        else:
            return False, capture_result["result"]
    
    return False, "未知错误：线程未正常结束"


@router.get("/camera-frame")
async def get_camera_frame(camera_id: str):
    """获取摄像头/视频的第一帧
    
    策略：
    1. 优先使用 camera.source（第二步保存的地址，通常是最新的）
    2. 如果打不开，且配置了 hikvision_config，重新获取 RTSP 地址并重试
    3. 返回成功或失败信息
    """
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
        # 步骤1：优先尝试使用已保存的 source（第二步获取的时效性地址）
        success, result = _try_capture_frame(camera.source, camera_id)
        if success:
            print(f"[CameraFrame] Camera {camera_id} frame captured using saved source: {camera.source}")
            return result
        
        print(f"[CameraFrame] Camera {camera_id} failed to open saved source: {result}")
        
        # 步骤2：如果失败且配置了 hikvision_config，重新获取 RTSP 地址
        if camera.hikvision_config:
            print(f"[CameraFrame] Camera {camera_id} retrying with hikvision_config...")
            config_dict = camera.hikvision_config.model_dump()
            rtsp_url = rtsp_client.get_stream_url(
                camera.hikvision_config.cameraIndexCode,
                config=config_dict
            )
            
            if rtsp_url:
                print(f"[CameraFrame] Camera {camera_id} got new RTSP: {rtsp_url}")
                success, result = _try_capture_frame(rtsp_url, camera_id)
                if success:
                    print(f"[CameraFrame] Camera {camera_id} frame captured with new RTSP")
                    # 更新 camera.source 为新的 RTSP 地址，下次可直接使用
                    camera.source = rtsp_url
                    config_manager.update_config(config)
                    print(f"[CameraFrame] Camera {camera_id} source updated to new RTSP")
                    return result
                else:
                    print(f"[CameraFrame] Camera {camera_id} failed to open new RTSP: {result}")
            else:
                print(f"[CameraFrame] Camera {camera_id} failed to get new RTSP from API")
        
        # 向后兼容：旧配置只有 camera_code
        elif camera.camera_code:
            print(f"[CameraFrame] Camera {camera_id} retrying with camera_code...")
            rtsp_url = rtsp_client.get_stream_url(camera.camera_code)
            
            if rtsp_url:
                success, result = _try_capture_frame(rtsp_url, camera_id)
                if success:
                    # 更新 camera.source 为新的 RTSP 地址
                    camera.source = rtsp_url
                    config_manager.update_config(config)
                    print(f"[CameraFrame] Camera {camera_id} source updated to new RTSP")
                    return result
        
        # 所有尝试都失败
        raise HTTPException(
            status_code=400, 
            detail=f"无法获取摄像头画面。已尝试 source={camera.source}"
            + (f" 和重新获取RTSP" if camera.hikvision_config or camera.camera_code else "")
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[CameraFrame] Camera {camera_id} unexpected error: {e}")
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
    获取视频文件信息 - 使用 ffmpeg
    """
    try:
        from app.services.video_stream import _find_ffmpeg
        ffmpeg_path = _find_ffmpeg()
        if not ffmpeg_path:
            raise HTTPException(
                status_code=500, detail="ffmpeg not found"
            )
        
        # 使用 ffprobe 获取视频信息
        ffprobe_path = ffmpeg_path.replace("ffmpeg", "ffprobe")
        if not os.path.exists(ffprobe_path):
            ffprobe_path = shutil.which("ffprobe")
        
        if not ffprobe_path or not os.path.exists(ffprobe_path):
            raise HTTPException(
                status_code=500, detail="ffprobe not found"
            )
        
        cmd = [
            ffprobe_path,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,nb_frames",
            "-of", "json",
            video_path
        ]
        
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        
        if result.returncode != 0:
            raise HTTPException(
                status_code=400, detail=f"无法获取视频信息: {result.stderr}"
            )
        
        import json
        data = json.loads(result.stdout)
        stream = data.get("streams", [{}])[0]
        
        width = stream.get("width", 0)
        height = stream.get("height", 0)
        fps_str = stream.get("r_frame_rate", "25/1")
        if "/" in fps_str:
            num, den = fps_str.split("/")
            fps = float(num) / float(den)
        else:
            fps = float(fps_str)
        
        total_frames_str = stream.get("nb_frames", "0")
        try:
            total_frames = int(total_frames_str)
        except:
            total_frames = 0
        
        info = {
            "path": video_path,
            "total_frames": total_frames,
            "fps": fps,
            "width": width,
            "height": height,
            "duration": total_frames / fps if fps > 0 and total_frames > 0 else 0,
        }

        return info

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取视频信息失败: {str(e)}")
