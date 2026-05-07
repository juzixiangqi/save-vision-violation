"""
RTSP流诊断测试 - 精确定位代码逻辑问题

这个测试文件用于：
1. 通过海康威视API获取RTSP流地址
2. 单帧捕获 + 模型API检测（合并测试）
3. 3秒视频流处理（每6帧处理一次）
4. 完善的日志记录每个步骤的耗时和状态

运行方式:
    # 直接运行（使用默认摄像头代码）
    uv run python backend/test_rtsp_diagnosis.py
    
    # 或者指定其他摄像头代码
    uv run python backend/test_rtsp_diagnosis.py <camera_code>
    
    # 或者使用环境变量
    $env:HIK_CAMERA_CODE="your-camera-code"
    uv run python backend/test_rtsp_diagnosis.py

说明:
    - 问题一定是代码逻辑问题，而非模型API或超时设置
    - 本测试会详细记录每个环节的时间消耗
    - 特别关注: 海康API获取、ffmpeg读取、帧处理、API调用、并发控制
"""

import sys
import os
import time
import subprocess
import shutil
import json
import numpy as np
import cv2
import requests
from datetime import datetime
from collections import deque
from typing import Optional, List, Tuple, Dict


# 添加backend到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))


# 海康威视配置（固定配置）
HIKVISION_CONFIG = {
    "host": "https://10.190.11.240",
    "port": 443,
    "artemis": "artemis",
    "appKey": "25205625",
    "appSecret": "yvYgVYYfTcpXdSHHnIov",
    "method": "POST",
}

# 固定摄像头代码
DEFAULT_CAMERA_CODE = "b567c3277cc14d07b3d04fe9e2ed5af1"


# 模型API配置
MODEL_API_CONFIG = {
    "url": os.getenv("MODEL_API_URL", "http://10.190.28.23:31674/predict"),
    "timeout": int(os.getenv("MODEL_API_TIMEOUT", "30")),
    "imgsz": int(os.getenv("MODEL_API_IMGSZ", "640")),
    "confidence": float(os.getenv("MODEL_API_CONFIDENCE", "0.2")),
}


def log(msg: str, level: str = "INFO"):
    """统一日志格式"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [{level}] {msg}")


def find_ffmpeg() -> Optional[str]:
    """查找ffmpeg路径"""
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path
    
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
            return expanded
    return None


def get_hikvision_rtsp(camera_code: str, config: Dict = None) -> Tuple[bool, Optional[str], Dict]:
    """
    通过海康威视API获取RTSP流地址
    
    Args:
        camera_code: 摄像头indexCode
        config: 海康配置（默认使用HIKVISION_CONFIG）
    
    Returns:
        (success, rtsp_url, diagnostics)
    """
    import base64
    import hashlib
    import hmac
    import uuid
    
    cfg = config or HIKVISION_CONFIG
    
    diagnostics = {
        "camera_code": camera_code,
        "host": cfg["host"],
        "port": cfg["port"],
        "appKey": cfg["appKey"],
        "steps": [],
    }
    
    log("=" * 60)
    log("步骤1: 通过海康威视API获取RTSP流地址")
    log("=" * 60)
    log(f"摄像头代码: {camera_code}")
    log(f"海康服务器: {cfg['host']}:{cfg['port']}")
    
    api = "/api/video/v2/cameras/previewURLs"
    payload = {
        "cameraIndexCode": camera_code,
        "transmode": 1,
        "streamType": 0,
        "protocol": "rtsp",
    }
    
    url = f"{cfg['host']}:{cfg['port']}/{cfg['artemis']}{api}"
    
    # 生成签名
    try:
        timestamp = str(int(round(time.time() * 1000)))
        nonce = str(uuid.uuid1())
        secret = str(cfg["appSecret"]).encode("utf-8")
        message = str(
            cfg["method"]
            + "\n*/*\napplication/json\nx-ca-key:"
            + cfg["appKey"]
            + "\nx-ca-nonce:"
            + nonce
            + "\nx-ca-timestamp:"
            + timestamp
            + "\n/"
            + cfg["artemis"]
            + api
        ).encode("utf-8")
        signature = base64.b64encode(
            hmac.new(secret, message, digestmod=hashlib.sha256).digest()
        ).decode("utf-8")
        
        headers = {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "X-Ca-Key": cfg["appKey"],
            "X-Ca-Signature": signature,
            "X-Ca-timestamp": timestamp,
            "X-Ca-nonce": nonce,
            "X-Ca-Signature-Headers": "x-ca-key,x-ca-nonce,x-ca-timestamp",
        }
        
        diagnostics["signature"] = {"timestamp": timestamp, "nonce": nonce}
        
    except Exception as e:
        log(f"签名生成失败: {e}", "ERROR")
        return False, None, {**diagnostics, "error": f"signature failed: {e}"}
    
    # 发送请求
    request_start = time.time()
    try:
        log(f"发送请求到: {url}")
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            verify=False,
            timeout=10,
        )
        request_time = (time.time() - request_start) * 1000
        
        log(f"响应状态码: {response.status_code}, 耗时: {request_time:.1f}ms")
        diagnostics["api_call"] = {
            "status_code": response.status_code,
            "time_ms": request_time,
            "url": url,
        }
        
        if response.status_code != 200:
            log(f"请求失败: HTTP {response.status_code}", "ERROR")
            log(f"响应内容: {response.text[:500]}", "ERROR")
            return False, None, {**diagnostics, "error": f"HTTP {response.status_code}: {response.text[:200]}"}
        
        result = response.json()
        log(f"响应数据: {json.dumps(result, indent=2, ensure_ascii=False)}")
        diagnostics["response"] = result
        
        if result.get("code") == "0" and result.get("data") and result.get("data").get("url"):
            rtsp_url = result["data"]["url"]
            log(f"✓ 获取RTSP地址成功: {rtsp_url[:80]}...")
            return True, rtsp_url, diagnostics
        else:
            error_msg = result.get("msg", "未知错误")
            log(f"✗ API返回错误: {error_msg}", "ERROR")
            return False, None, {**diagnostics, "error": error_msg}
            
    except requests.exceptions.Timeout:
        request_time = (time.time() - request_start) * 1000
        log(f"请求超时 (耗时: {request_time:.1f}ms)", "ERROR")
        return False, None, {**diagnostics, "error": "timeout", "time_ms": request_time}
    except Exception as e:
        request_time = (time.time() - request_start) * 1000
        log(f"请求异常: {e} (耗时: {request_time:.1f}ms)", "ERROR")
        return False, None, {**diagnostics, "error": str(e), "time_ms": request_time}


def get_video_info(source: str, timeout: int = 8) -> Tuple[int, int, float]:
    """获取视频信息: 宽度, 高度, FPS
    
    Args:
        source: 视频源地址
        timeout: ffprobe超时时间（秒），默认8秒
    """
    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        raise Exception("ffmpeg not found")
    
    ffprobe_path = ffmpeg_path.replace("ffmpeg", "ffprobe")
    if not os.path.exists(ffprobe_path):
        ffprobe_path = shutil.which("ffprobe")
    
    if ffprobe_path and os.path.exists(ffprobe_path):
        try:
            # 使用更短的超时和更快的探测参数
            cmd = [
                ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate",
                "-of", "json",
                "-analyzeduration", "1000000",  # 分析时长1秒（默认5秒）
                "-probesize", "500000",  # 探测数据量500KB
                source
            ]
            
            # RTSP流需要特殊处理
            if source.startswith("rtsp://"):
                # 在输入前添加RTSP传输参数
                cmd = [
                    ffprobe_path,
                    "-v", "error",
                    "-rtsp_transport", "tcp",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=width,height,r_frame_rate",
                    "-of", "json",
                    "-analyzeduration", "1000000",
                    "-probesize", "500000",
                    source
                ]
            
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                   text=True, timeout=timeout)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                stream = data.get("streams", [{}])[0]
                width = stream.get("width", 1920)
                height = stream.get("height", 1080)
                fps_str = stream.get("r_frame_rate", "25/1")
                if "/" in fps_str:
                    num, den = fps_str.split("/")
                    fps = float(num) / float(den)
                else:
                    fps = float(fps_str)
                log(f"✓ ffprobe成功: {width}x{height} @ {fps}fps")
                return width, height, fps
            else:
                stderr = result.stderr[:200] if result.stderr else "unknown error"
                log(f"ffprobe返回错误: {stderr}", "WARN")
        except subprocess.TimeoutExpired:
            log(f"ffprobe探测超时({timeout}s): 视频流连接缓慢或不可用", "WARN")
        except Exception as e:
            log(f"ffprobe失败: {e}", "WARN")
    
    log("使用默认视频参数: 1920x1080 @ 25fps")
    return 1920, 1080, 25.0


def capture_and_detect_frame(source: str, timeout_ms: int = 10000) -> Tuple[bool, Optional[np.ndarray], Dict]:
    """
    捕获单帧并执行模型检测（合并TEST1和TEST2）
    
    步骤:
    1. 获取视频信息
    2. 使用ffmpeg捕获单帧
    3. 调用模型API检测
    4. 返回详细的时间消耗统计
    
    Returns:
        (success, frame, diagnostics)
    """
    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        return False, None, {"error": "ffmpeg not found"}
    
    diagnostics = {
        "source": source,
        "timeout_ms": timeout_ms,
        "steps": [],
    }
    
    log("=" * 60)
    log("合并测试: 单帧捕获 + 模型检测")
    log("=" * 60)
    
    # 步骤1: 获取视频信息
    try:
        info_start = time.time()
        width, height, fps = get_video_info(source)
        info_time = (time.time() - info_start) * 1000
        log(f"视频信息: {width}x{height} @ {fps}fps (获取耗时: {info_time:.1f}ms)")
        diagnostics["video_info"] = {"width": width, "height": height, "fps": fps, "time_ms": info_time}
    except Exception as e:
        log(f"获取视频信息失败: {e}", "ERROR")
        return False, None, {**diagnostics, "error": f"video info failed: {e}"}
    
    # 步骤2: 使用ffmpeg持续读取方式捕获帧（与VideoStream一致）
    log("-" * 40)
    log("步骤2: 捕获单帧（持续读取模式）")
    log("-" * 40)
    log("注意: RTSP连接建立本身需要1-3秒，这是正常的")
    log("      只有连接建立后，后续帧读取才是毫秒级")
    
    # 与VideoStream一致：使用rawvideo持续读取
    # 优势：连接建立后，帧读取是毫秒级
    cmd = [
        ffmpeg_path,
        "-rtsp_transport", "tcp",
        "-i", source,
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-s", f"{width}x{height}",
        "-"
    ]
    
    log(f"FFmpeg命令: {' '.join(cmd)}")
    log(f"模式: 持续读取rawvideo (与VideoStream一致)")
    
    capture_diagnostics = {
        "launch_ms": 0,
        "first_frame_total_ms": 0,
        "first_frame_read_ms": 0,
        "second_frame_read_ms": 0,
        "connect_established": False,
    }
    
    capture_start = time.time()
    process = None
    
    try:
        # 启动ffmpeg持续进程
        log("启动ffmpeg持续进程...")
        launch_start = time.time()
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=frame_size * 2,
        )
        launch_time = (time.time() - launch_start) * 1000
        capture_diagnostics["launch_ms"] = launch_time
        log(f"ffmpeg进程启动耗时: {launch_time:.1f}ms (PID: {process.pid})")
        
        # 读取第一帧（包含RTSP连接建立时间）
        log("等待第一帧（包含RTSP连接建立）...")
        import threading
        
        frame_buffer = [None]
        def _read_first_frame():
            try:
                frame_buffer[0] = process.stdout.read(frame_size)
            except Exception as e:
                frame_buffer[0] = e
        
        read_thread = threading.Thread(target=_read_first_frame)
        read_thread.daemon = True
        read_thread.start()
        
        # 等待第一帧，最多10秒
        first_frame_timeout = 10.0
        read_thread.join(timeout=first_frame_timeout)
        
        first_frame_time = (time.time() - capture_start) * 1000
        capture_diagnostics["first_frame_total_ms"] = first_frame_time
        
        if read_thread.is_alive():
            log(f"✗ 第一帧读取超时 (>{first_frame_timeout}s)", "ERROR")
            process.terminate()
            return False, None, {**diagnostics, "error": f"first frame timeout after {first_frame_timeout}s"}
        
        raw_frame1 = frame_buffer[0]
        if isinstance(raw_frame1, Exception):
            raise raw_frame1
        
        if not raw_frame1 or len(raw_frame1) < frame_size:
            log(f"✗ 第一帧数据不完整: {len(raw_frame1) if raw_frame1 else 0}/{frame_size} bytes", "ERROR")
            process.terminate()
            return False, None, {**diagnostics, "error": f"incomplete first frame: {len(raw_frame1) if raw_frame1 else 0}/{frame_size}"}
        
        # 解码第一帧
        decode_start = time.time()
        frame = np.frombuffer(raw_frame1, dtype=np.uint8).reshape((height, width, 3))
        decode_time = (time.time() - decode_start) * 1000
        
        capture_diagnostics["connect_established"] = True
        log(f"✓ 第一帧成功: {frame.shape}")
        log(f"  首帧总耗时(含连接): {first_frame_time:.1f}ms")
        log(f"  解码耗时: {decode_time:.1f}ms")
        
        # 尝试读取第二帧，测量纯读取时间（不含连接建立）
        log("读取第二帧（测量纯读取耗时）...")
        read2_start = time.time()
        
        frame_buffer2 = [None]
        def _read_second_frame():
            try:
                frame_buffer2[0] = process.stdout.read(frame_size)
            except Exception as e:
                frame_buffer2[0] = e
        
        read_thread2 = threading.Thread(target=_read_second_frame)
        read_thread2.daemon = True
        read_thread2.start()
        read_thread2.join(timeout=1.0)  # 第二帧应该很快
        
        second_read_time = (time.time() - read2_start) * 1000
        capture_diagnostics["second_frame_read_ms"] = second_read_time
        
        if not read_thread2.is_alive() and frame_buffer2[0] and len(frame_buffer2[0]) == frame_size:
            log(f"✓ 第二帧读取耗时: {second_read_time:.1f}ms (纯读取，不含连接)")
        else:
            log(f"⚠ 第二帧读取失败或超时，跳过", "WARN")
        
        # 停止ffmpeg
        process.terminate()
        try:
            process.wait(timeout=2)
        except:
            process.kill()
        
        total_time = (time.time() - capture_start) * 1000
        log(f"  ffmpeg总运行时间: {total_time:.1f}ms")
        
        # 分析耗时
        connect_time = first_frame_time - second_read_time if second_read_time > 0 else first_frame_time * 0.8
        log(f"\n耗时分析:")
        log(f"  RTSP连接建立: ~{connect_time:.1f}ms (这是正常的，TCP+RTSP协商)")
        log(f"  帧读取(建立后): ~{second_read_time:.1f}ms (这才是真实的帧读取速度)")
        log(f"  连接建立后帧读取 ≈ {second_read_time:.1f}ms/帧")
        
        diagnostics["capture"] = {
            "total_ms": total_time,
            "first_frame_ms": first_frame_time,
            "second_frame_ms": second_read_time,
            "connect_estimated_ms": connect_time,
            "decode_ms": decode_time,
            "shape": frame.shape,
            "mode": "continuous_read",
        }
        
    except subprocess.TimeoutExpired as e:
        capture_time = (time.time() - capture_start) * 1000
        log(f"✗ ffmpeg执行超时: {e}", "ERROR")
        if process:
            process.terminate()
        return False, None, {**diagnostics, "error": "ffmpeg timeout"}
    except Exception as e:
        capture_time = (time.time() - capture_start) * 1000
        log(f"帧捕获异常: {e} (总耗时: {capture_time:.1f}ms)", "ERROR")
        import traceback
        traceback.print_exc()
        if process:
            process.terminate()
        return False, None, {**diagnostics, "error": str(e)}
    
    # 步骤3: 模型API检测
    log("-" * 40)
    log("步骤3: 模型API检测")
    log("-" * 40)
    
    detect_success, detect_diag = detect_frame_api(frame, diagnostics)
    
    if detect_success:
        # 保存帧用于检查
        save_path = "test_frame_capture.jpg"
        cv2.imwrite(save_path, frame)
        log(f"✓ 帧已保存到: {save_path}")
        
        total_time = (time.time() - capture_start) * 1000
        log(f"\n✓ 合并测试完成！总耗时: {total_time:.1f}ms")
        
        return True, frame, diagnostics
    else:
        return False, frame, detect_diag


def detect_frame_api(frame: np.ndarray, diagnostics: Dict = None) -> Tuple[bool, Dict]:
    """
    调用模型API检测单帧
    
    Args:
        frame: OpenCV图像 (BGR格式)
        diagnostics: 可选的诊断信息字典
    
    Returns:
        (success, diagnostics)
    """
    if diagnostics is None:
        diagnostics = {}
    
    api_start = time.time()
    try:
        # 编码图像
        encode_start = time.time()
        success, img_encoded = cv2.imencode(".jpg", frame)
        encode_time = (time.time() - encode_start) * 1000
        
        if not success:
            log("图像编码失败", "ERROR")
            return False, {**diagnostics, "error": "图像编码失败"}
        
        img_size_kb = len(img_encoded.tobytes()) / 1024
        log(f"图像编码: {frame.shape[1]}x{frame.shape[0]} ({img_size_kb:.1f}KB, 耗时: {encode_time:.1f}ms)")
        
        # 准备请求数据
        import io
        files = {
            "file": ("image.jpg", io.BytesIO(img_encoded.tobytes()), "image/jpeg")
        }
        data = {
            "imgsz": str(MODEL_API_CONFIG["imgsz"]),
            "conf": str(MODEL_API_CONFIG["confidence"]),
        }
        
        # 发送HTTP请求
        log(f"发送请求到: {MODEL_API_CONFIG['url']} (timeout={MODEL_API_CONFIG['timeout']}s)...")
        request_start = time.time()
        
        session = requests.Session()
        response = session.post(
            MODEL_API_CONFIG["url"],
            files=files,
            data=data,
            timeout=MODEL_API_CONFIG["timeout"],
        )
        request_time = (time.time() - request_start) * 1000
        
        log(f"HTTP响应: status={response.status_code}, 耗时: {request_time:.1f}ms")
        response.raise_for_status()
        
        # 解析JSON
        parse_start = time.time()
        result = response.json()
        parse_time = (time.time() - parse_start) * 1000
        
        api_time = (time.time() - api_start) * 1000
        
        log(f"API响应状态: {result.get('status', 'unknown')}")
        log(f"检测到目标数: {len(result.get('predictions', []))}")
        log(f"  API总耗时: {api_time:.1f}ms")
        log(f"  编码耗时: {encode_time:.1f}ms")
        log(f"  请求耗时: {request_time:.1f}ms")
        log(f"  解析耗时: {parse_time:.1f}ms")
        
        diagnostics["detection"] = {
            "total_ms": api_time,
            "encode_ms": encode_time,
            "request_ms": request_time,
            "parse_ms": parse_time,
            "status": result.get("status"),
            "predictions_count": len(result.get("predictions", [])),
            "image_size_kb": img_size_kb,
        }
        
        return True, diagnostics
        
    except requests.exceptions.ConnectionError as e:
        api_time = (time.time() - api_start) * 1000
        log(f"连接错误: {e} (API耗时: {api_time:.1f}ms)", "ERROR")
        return False, {**diagnostics, "error": f"ConnectionError: {e}"}
    except requests.exceptions.Timeout as e:
        api_time = (time.time() - api_start) * 1000
        log(f"请求超时: {e} (API耗时: {api_time:.1f}ms)", "ERROR")
        return False, {**diagnostics, "error": f"Timeout: {e}"}
    except Exception as e:
        api_time = (time.time() - api_start) * 1000
        log(f"API调用异常: {e} (API耗时: {api_time:.1f}ms)", "ERROR")
        import traceback
        traceback.print_exc()
        return False, {**diagnostics, "error": str(e)}


def test_stream_processing(source: str, duration_seconds: int = 3, detection_interval: int = 6, refresh_rtsp_callback=None):
    """
    测试视频流处理（模拟完整的处理逻辑）
    
    每隔detection_interval帧处理一次，其他帧丢弃
    运行duration_seconds秒
    
    Args:
        source: RTSP流地址
        duration_seconds: 测试时长（秒）
        detection_interval: 检测间隔（帧）
        refresh_rtsp_callback: 刷新RTSP地址的回调函数，当流断开时调用
    """
    log("\n" + "=" * 60)
    log(f"流处理测试 ({duration_seconds}秒, 每{detection_interval}帧检测一次)")
    log("=" * 60)
    
    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        log("ffmpeg not found", "ERROR")
        return
    
    # 获取视频信息
    try:
        width, height, fps = get_video_info(source)
        log(f"视频信息: {width}x{height} @ {fps:.1f}fps")
    except Exception as e:
        log(f"获取视频信息失败: {e}", "ERROR")
        return
    
    frame_size = width * height * 3
    expected_frame_interval = 1.0 / fps if fps > 0 else 0.04
    
    # 构建ffmpeg命令（持续读取）
    # 注意：不在ffmpeg命令中添加超时参数，超时控制在Python中实现
    # ffmpeg的超时参数(-stimeout, -timeout)在某些版本中行为不一致
    
    cmd = [
        ffmpeg_path,
        "-rtsp_transport", "tcp",
        "-i", source,
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-s", f"{width}x{height}",
        "-"
    ]
    
    if source.endswith((".mp4", ".avi", ".mkv")):
        # 本地视频
        cmd = [
            ffmpeg_path,
            "-i", source,
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}",
            "-"
        ]
    
    log(f"FFmpeg命令: {' '.join(cmd)}")
    
    # 统计信息
    stats = {
        "total_frames_read": 0,
        "frames_processed": 0,
        "frames_skipped": 0,
        "detections_attempted": 0,
        "detections_success": 0,
        "detections_failed": 0,
        "frame_intervals": deque(maxlen=100),
        "read_times": deque(maxlen=100),
        "process_times": deque(maxlen=100),
        "api_times": deque(maxlen=100),
        "errors": [],
    }
    
    # 启动ffmpeg
    try:
        log("启动ffmpeg进程...")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=frame_size * 10,
        )
        log(f"ffmpeg进程已启动 (PID: {process.pid})")
    except Exception as e:
        log(f"启动ffmpeg失败: {e}", "ERROR")
        return
    
    start_time = time.time()
    last_frame_time = start_time
    frame_number = 0
    detection_frame_number = 0
    last_detection_result = None
    
    try:
        log(f"开始处理... (目标时长: {duration_seconds}秒)")
        
        while time.time() - start_time < duration_seconds:
            # 检查ffmpeg是否存活
            if process.poll() is not None:
                exit_code = process.poll()
                log(f"ffmpeg进程已退出 (exit code: {exit_code})", "ERROR")
                stats["errors"].append(f"ffmpeg exited with code {exit_code}")
                
                # 尝试刷新RTSP地址并重新连接
                if refresh_rtsp_callback:
                    log("尝试刷新RTSP地址...", "WARN")
                    new_source = refresh_rtsp_callback()
                    if new_source:
                        log(f"获取到新地址，重新启动ffmpeg...")
                        # 使用新地址重新启动
                        cmd[cmd.index("-i") + 1] = new_source
                        try:
                            process = subprocess.Popen(
                                cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                bufsize=frame_size * 10,
                            )
                            log(f"ffmpeg已重新启动 (PID: {process.pid})")
                            continue  # 继续循环
                        except Exception as e:
                            log(f"重新启动ffmpeg失败: {e}", "ERROR")
                
                break
            
            # 读取帧（带超时，防止卡死）
            import threading
            read_start = time.time()
            frame_buffer = [None]
            
            def _read_frame():
                try:
                    frame_buffer[0] = process.stdout.read(frame_size)
                except Exception as e:
                    frame_buffer[0] = e
            
            read_thread = threading.Thread(target=_read_frame)
            read_thread.daemon = True
            read_thread.start()
            read_thread.join(timeout=3.0)  # 最多等待3秒读取一帧
            
            if read_thread.is_alive():
                log(f"读取帧超时 (>{3.0}s)，视频流可能已断开", "WARN")
                stats["errors"].append("frame read timeout (>3s)")
                # 终止ffmpeg进程，避免残留
                try:
                    process.terminate()
                    process.wait(timeout=2)
                except:
                    process.kill()
                
                # 尝试刷新RTSP地址并重新连接
                if refresh_rtsp_callback:
                    log("尝试刷新RTSP地址...", "WARN")
                    new_source = refresh_rtsp_callback()
                    if new_source:
                        log(f"获取到新地址，重新启动ffmpeg...")
                        # 使用新地址重新启动
                        cmd[cmd.index("-i") + 1] = new_source
                        try:
                            process = subprocess.Popen(
                                cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                bufsize=frame_size * 10,
                            )
                            log(f"ffmpeg已重新启动 (PID: {process.pid})")
                            continue  # 继续循环
                        except Exception as e:
                            log(f"重新启动ffmpeg失败: {e}", "ERROR")
                
                break
            
            raw_frame = frame_buffer[0]
            read_time = (time.time() - read_start) * 1000
            stats["read_times"].append(read_time)
            
            if isinstance(raw_frame, Exception):
                stats["errors"].append(f"read exception: {raw_frame}")
                continue
            
            if not raw_frame or len(raw_frame) < frame_size:
                stats["errors"].append(f"incomplete frame: {len(raw_frame) if raw_frame else 0}/{frame_size}")
                continue
            
            frame_number += 1
            stats["total_frames_read"] += 1
            
            # 计算帧间隔
            current_time = time.time()
            frame_interval = current_time - last_frame_time
            last_frame_time = current_time
            stats["frame_intervals"].append(frame_interval)
            
            # 每30帧打印一次读取状态
            if frame_number % 30 == 0:
                avg_interval = sum(stats["frame_intervals"]) / len(stats["frame_intervals"])
                avg_read_time = sum(stats["read_times"]) / len(stats["read_times"])
                elapsed = current_time - start_time
                log(f"状态报告 [t={elapsed:.1f}s]: 已读取{frame_number}帧, "
                    f"平均帧间隔={avg_interval*1000:.1f}ms, "
                    f"平均读取耗时={avg_read_time:.1f}ms")
            
            # 跳帧逻辑
            detection_frame_number += 1
            if detection_frame_number % detection_interval != 0:
                stats["frames_skipped"] += 1
                continue
            
            # 处理帧
            stats["frames_processed"] += 1
            process_start = time.time()
            
            try:
                # 解码帧
                decode_start = time.time()
                frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((height, width, 3))
                decode_time = (time.time() - decode_start) * 1000
                
                # 实际调用模型API检测
                detect_success, detect_diag = detect_frame_api(frame)
                
                detect_time = detect_diag.get("detection", {}).get("total_ms", 0) if detect_success else 0
                predictions_count = detect_diag.get("detection", {}).get("predictions_count", 0) if detect_success else 0
                
                process_time = (time.time() - process_start) * 1000
                stats["process_times"].append(process_time)
                
                if detect_success:
                    stats["detections_success"] += 1
                    log(f"处理帧 #{frame_number}: 解码={decode_time:.1f}ms, "
                        f"API检测={detect_time:.1f}ms, "
                        f"检测到{predictions_count}个目标, "
                        f"总处理={process_time:.1f}ms")
                else:
                    stats["detections_failed"] += 1
                    error_msg = detect_diag.get("error", "未知错误")
                    log(f"处理帧 #{frame_number} 检测失败: {error_msg}, "
                        f"解码={decode_time:.1f}ms, "
                        f"总处理={process_time:.1f}ms", "WARN")
                
            except Exception as e:
                stats["detections_failed"] += 1
                log(f"处理帧 #{frame_number} 失败: {e}", "ERROR")
                stats["errors"].append(f"frame {frame_number}: {e}")
        
        # 结束处理
        total_time = time.time() - start_time
        log("\n" + "=" * 60)
        log("处理完成，统计报告:")
        log("=" * 60)
        
        # 计算统计数据
        if stats["frame_intervals"]:
            avg_interval = sum(stats["frame_intervals"]) / len(stats["frame_intervals"])
            max_interval = max(stats["frame_intervals"])
            min_interval = min(stats["frame_intervals"])
        else:
            avg_interval = max_interval = min_interval = 0
        
        if stats["read_times"]:
            avg_read = sum(stats["read_times"]) / len(stats["read_times"])
            max_read = max(stats["read_times"])
        else:
            avg_read = max_read = 0
        
        if stats["process_times"]:
            avg_process = sum(stats["process_times"]) / len(stats["process_times"])
            max_process = max(stats["process_times"])
        else:
            avg_process = max_process = 0
        
        expected_frames = int(fps * duration_seconds)
        actual_fps = frame_number / total_time if total_time > 0 else 0
        
        log(f"运行时长: {total_time:.2f}s (目标: {duration_seconds}s)")
        log(f"视频FPS: {fps:.1f}, 实际读取FPS: {actual_fps:.1f}")
        log(f"预期帧数: {expected_frames}, 实际读取: {frame_number}")
        log(f"总读取帧: {stats['total_frames_read']}")
        log(f"处理帧数: {stats['frames_processed']}")
        log(f"跳过帧数: {stats['frames_skipped']}")
        log(f"帧间隔: avg={avg_interval*1000:.1f}ms, max={max_interval*1000:.1f}ms, min={min_interval*1000:.1f}ms")
        log(f"读取耗时: avg={avg_read:.1f}ms, max={max_read:.1f}ms")
        log(f"处理耗时: avg={avg_process:.1f}ms, max={max_process:.1f}ms")
        
        if stats["errors"]:
            log(f"错误数: {len(stats['errors'])}")
            for i, error in enumerate(stats["errors"][:5]):
                log(f"  错误{i+1}: {error}", "WARN")
        
        # 诊断分析
        log("\n诊断分析:")
        if avg_interval > expected_frame_interval * 2:
            log(f"⚠️ 帧间隔异常: 平均{avg_interval*1000:.1f}ms > 预期{expected_frame_interval*1000:.1f}ms", "WARN")
        
        if max_interval > 0.5:
            log(f"⚠️ 存在卡顿: 最大帧间隔{max_interval*1000:.1f}ms > 500ms", "WARN")
        
        if stats["frames_processed"] == 0:
            log("❌ 没有帧被处理！", "ERROR")
        
        if avg_read > 50:
            log(f"⚠️ 读取耗时过长: avg={avg_read:.1f}ms", "WARN")
            
    except KeyboardInterrupt:
        log("用户中断", "WARN")
    except Exception as e:
        log(f"处理异常: {e}", "ERROR")
        import traceback
        traceback.print_exc()
    finally:
        if process:
            try:
                process.terminate()
                process.wait(timeout=2)
            except:
                process.kill()
        log("ffmpeg进程已终止")


def main():
    """主函数"""
    log("=" * 60)
    log("RTSP流诊断测试开始")
    log("=" * 60)
    log(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"Python: {sys.version}")
    log(f"OpenCV: {cv2.__version__}")
    log(f"NumPy: {np.__version__}")
    log(f"Requests: {requests.__version__}")
    
    # 检查ffmpeg
    ffmpeg_path = find_ffmpeg()
    if ffmpeg_path:
        log(f"FFmpeg: {ffmpeg_path}")
        try:
            result = subprocess.run([ffmpeg_path, "-version"], stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE, text=True, timeout=5)
            version_line = result.stdout.split('\n')[0]
            log(f"FFmpeg版本: {version_line}")
        except:
            pass
    else:
        log("FFmpeg: NOT FOUND", "ERROR")
        return
    
    # 获取camera_code（优先使用命令行参数，其次环境变量，最后使用默认值）
    camera_code = DEFAULT_CAMERA_CODE
    if len(sys.argv) > 1:
        camera_code = sys.argv[1]
        log(f"使用命令行参数的摄像头代码: {camera_code}")
    elif os.getenv("HIK_CAMERA_CODE"):
        camera_code = os.getenv("HIK_CAMERA_CODE")
        log(f"使用环境变量的摄像头代码: {camera_code}")
    else:
        log(f"使用默认摄像头代码: {camera_code}")
    
    log(f"摄像头代码: {camera_code}")
    
    def get_fresh_rtsp_url(max_retries: int = 3) -> Optional[str]:
        """获取最新的RTSP流地址，支持重试
        
        RTSP地址有时效性，每次使用前都需要获取最新的
        """
        for attempt in range(max_retries):
            if attempt > 0:
                log(f"第{attempt + 1}次尝试获取RTSP地址...")
                time.sleep(1)  # 重试前等待1秒
            
            success, rtsp_url, diag = get_hikvision_rtsp(camera_code)
            if success and rtsp_url:
                log(f"✓ 获取RTSP地址成功: {rtsp_url[:80]}...")
                return rtsp_url
            else:
                log(f"✗ 获取RTSP地址失败 (尝试 {attempt + 1}/{max_retries})", "ERROR")
        
        log(f"✗ 获取RTSP地址失败，已重试{max_retries}次", "ERROR")
        return None
    
    # 测试1: 单帧捕获 + 模型检测
    log("\n" + "=" * 60)
    log("测试1: 单帧捕获 + 模型检测")
    log("=" * 60)
    
    # 获取最新的RTSP地址
    rtsp_url = get_fresh_rtsp_url()
    if not rtsp_url:
        log("无法获取RTSP地址，终止测试", "ERROR")
        return
    
    success, frame, diag = capture_and_detect_frame(rtsp_url)
    
    if success:
        log("✓ 单帧捕获和检测成功")
    else:
        error_msg = diag.get("error", "")
        log(f"✗ 单帧捕获或检测失败: {error_msg}", "ERROR")
        
        # 如果是超时或连接问题，尝试重新获取RTSP地址并重试
        if "timeout" in error_msg.lower() or "failed" in error_msg.lower():
            log("检测到RTSP流可能已过期，尝试重新获取...", "WARN")
            rtsp_url = get_fresh_rtsp_url()
            if rtsp_url:
                log("使用新的RTSP地址重试...")
                success, frame, diag = capture_and_detect_frame(rtsp_url)
                if success:
                    log("✓ 重试成功")
                else:
                    log(f"✗ 重试失败: {diag.get('error', '')}", "ERROR")
        
        if not success:
            log(f"诊断信息: {json.dumps(diag, indent=2, default=str)}")
    
    # 测试2: 流处理测试（3秒）
    log("\n" + "=" * 60)
    log("测试2: 流处理测试（3秒）")
    log("=" * 60)
    
    # 再次获取最新的RTSP地址（因为之前的可能已经过期）
    rtsp_url = get_fresh_rtsp_url()
    if not rtsp_url:
        log("无法获取RTSP地址，跳过流处理测试", "ERROR")
    else:
        # 传入刷新回调函数，当流断开时自动获取新地址
        test_stream_processing(
            rtsp_url, 
            duration_seconds=3, 
            detection_interval=6,
            refresh_rtsp_callback=get_fresh_rtsp_url
        )
    
    log("\n" + "=" * 60)
    log("所有测试完成")
    log("=" * 60)


if __name__ == "__main__":
    main()
