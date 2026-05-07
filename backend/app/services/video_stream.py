import numpy as np
import threading
import time
import asyncio
import platform
import os
import subprocess
import shutil
import select
from collections import deque
from typing import Callable, Optional, Union
from datetime import datetime


def _find_ffmpeg() -> Optional[str]:
    """查找 ffmpeg 可执行文件路径"""
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path
    
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
            return expanded
    
    return None


class VideoStream:
    """视频流处理器 - 使用 ffmpeg 命令行持续读取帧"""

    def __init__(
        self,
        source: str,
        camera_id: str,
        frame_callback: Optional[Callable] = None,
        detection_interval: int = 5,
        async_callback: bool = False,
    ):
        self.source = source
        self.camera_id = camera_id
        self.frame_callback = frame_callback
        self.detection_interval = detection_interval
        self.async_callback = async_callback
        self.running = False
        self.thread = None
        self.fps = 0
        self.frame_count = 0
        self.detection_frame_count = 0
        self.last_fps_time = time.time()
        self._loop = None
        self._ffmpeg_process = None
        self._ffmpeg_path = _find_ffmpeg()
        self._frame_width = 0
        self._frame_height = 0
        
        # 诊断统计
        self._read_timeouts = 0
        self._reconnect_count = 0
        self._last_read_time = 0.0
        self._last_frame_time = 0.0
        self._frame_intervals = deque(maxlen=10)  # 记录最近10帧间隔

    def start(self):
        """启动视频流"""
        if not self._ffmpeg_path:
            raise Exception("ffmpeg not found. Please install ffmpeg and ensure it's in PATH.")
        
        self.running = True

        # 如果使用异步回调，获取事件循环
        if self.async_callback:
            try:
                self._loop = asyncio.get_event_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)

        self.thread = threading.Thread(target=self._process_frames)
        self.thread.start()
        print(
            f"[VideoStream] Started camera {self.camera_id} (async={self.async_callback})"
        )

    def _process_frames(self):
        """使用 ffmpeg 持续读取并处理视频帧"""
        # 先启动 ffmpeg 获取视频信息（分辨率和帧率）
        probe_cmd = [
            self._ffmpeg_path,
            "-rtsp_transport", "tcp",
            "-i", self.source,
            "-vframes", "1",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-"
        ]
        
        try:
            # 先探测一帧获取分辨率（stderr 必须丢弃，否则管道阻塞导致死锁）
            probe_process = subprocess.Popen(
                probe_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            probe_data = probe_process.stdout.read()
            probe_process.wait(timeout=10)

            if len(probe_data) >= 100:
                # 尝试常见分辨率
                for w, h in [(1920, 1080), (1280, 720), (640, 480)]:
                    expected_size = w * h * 3
                    if len(probe_data) == expected_size:
                        self._frame_width = w
                        self._frame_height = h
                        break
            
            if self._frame_width == 0 or self._frame_height == 0:
                print(f"[VideoStream] Could not detect resolution for {self.camera_id}, using default 1920x1080")
                self._frame_width = 1920
                self._frame_height = 1080
            
            print(f"[VideoStream] Camera {self.camera_id} resolution: {self._frame_width}x{self._frame_height}")
            
        except Exception as e:
            print(f"[VideoStream] Probe error for {self.camera_id}: {e}")
            self._frame_width = 1920
            self._frame_height = 1080
        
        # 启动持续读取的 ffmpeg 进程
        frame_size = self._frame_width * self._frame_height * 3
        
        cmd = [
            self._ffmpeg_path,
            "-rtsp_transport", "tcp",
            "-i", self.source,
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{self._frame_width}x{self._frame_height}",
            "-"
        ]
        
        # 对于本地视频文件，不需要 rtsp_transport
        if isinstance(self.source, str) and self.source.endswith((".mp4", ".avi", ".mkv")):
            cmd = [
                self._ffmpeg_path,
                "-i", self.source,
                "-f", "rawvideo",
                "-pix_fmt", "bgr24",
                "-s", f"{self._frame_width}x{self._frame_height}",
                "-"
            ]
        
        try:
            self._ffmpeg_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,  # 不读取stderr，避免管道阻塞导致ffmpeg死锁
                bufsize=frame_size * 2,  # 缓冲2帧
            )
            
            print(f"[VideoStream] ffmpeg started for {self.camera_id}")
            
            consecutive_timeouts = 0
            
            while self.running:
                # 检查ffmpeg进程是否仍然存活
                if self._ffmpeg_process.poll() is not None:
                    exit_code = self._ffmpeg_process.poll()
                    print(f"[VideoStream] ffmpeg进程已退出 (exit code: {exit_code})，camera={self.camera_id}")
                    self._reconnect_count += 1
                    time.sleep(1.0)
                    self._ffmpeg_process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        bufsize=frame_size * 10,  # 增加缓冲到10帧
                    )
                    continue
                
                # 使用select检查数据是否可读（避免永久阻塞）
                read_start = time.time()
                readable = False
                try:
                    # 在Windows上select只支持socket，不支持pipe
                    # 所以使用超时读取策略
                    if platform.system() == "Windows":
                        # Windows: 使用线程进行超时读取
                        import threading
                        frame_buffer = [None]
                        def _read_frame():
                            frame_buffer[0] = self._ffmpeg_process.stdout.read(frame_size)
                        read_thread = threading.Thread(target=_read_frame)
                        read_thread.daemon = True
                        read_thread.start()
                        read_thread.join(timeout=5.0)  # 最多等待5秒
                        if read_thread.is_alive():
                            # 读取超时
                            consecutive_timeouts += 1
                            self._read_timeouts += 1
                            print(f"[VideoStream] 读取超时 #{consecutive_timeouts} (camera={self.camera_id}), "
                                  f"上次成功读取: {self._last_read_time:.3f}s前, "
                                  f"总超时次数: {self._read_timeouts}")
                            if consecutive_timeouts >= 3:
                                print(f"[VideoStream] 连续超时3次，重启ffmpeg进程 camera={self.camera_id}")
                                self._ffmpeg_process.terminate()
                                time.sleep(0.5)
                                self._ffmpeg_process = subprocess.Popen(
                                    cmd,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL,
                                    bufsize=frame_size * 10,
                                )
                                consecutive_timeouts = 0
                            time.sleep(0.5)
                            continue
                        raw_frame = frame_buffer[0]
                    else:
                        # Linux/Mac: 可以使用select
                        readable, _, _ = select.select([self._ffmpeg_process.stdout], [], [], 5.0)
                        if not readable:
                            consecutive_timeouts += 1
                            self._read_timeouts += 1
                            print(f"[VideoStream] 读取超时 #{consecutive_timeouts} (camera={self.camera_id})")
                            if consecutive_timeouts >= 3:
                                print(f"[VideoStream] 连续超时3次，重启ffmpeg进程 camera={self.camera_id}")
                                self._ffmpeg_process.terminate()
                                time.sleep(0.5)
                                self._ffmpeg_process = subprocess.Popen(
                                    cmd,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL,
                                    bufsize=frame_size * 10,
                                )
                                consecutive_timeouts = 0
                            continue
                        raw_frame = self._ffmpeg_process.stdout.read(frame_size)
                except Exception as e:
                    print(f"[VideoStream] 读取异常 camera={self.camera_id}: {e}")
                    time.sleep(1.0)
                    continue
                
                read_time = time.time() - read_start
                self._last_read_time = time.time()
                
                if read_time > 1.0:
                    print(f"[VideoStream] 帧读取耗时过长: {read_time:.3f}s camera={self.camera_id}")
                
                if not raw_frame or len(raw_frame) < frame_size:
                    # 视频结束或读取失败
                    print(f"[VideoStream] 读取到不完整帧: {len(raw_frame) if raw_frame else 0}/{frame_size} bytes")
                    if isinstance(self.source, str) and self.source.endswith((".mp4", ".avi", ".mkv")):
                        # 本地视频循环播放：重启 ffmpeg
                        print(f"[VideoStream] Local video ended, restarting...")
                        self._ffmpeg_process.terminate()
                        time.sleep(0.5)
                        self._ffmpeg_process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,
                            bufsize=frame_size * 10,
                        )
                        continue
                    else:
                        # RTSP 流断开，等待后重试
                        self._reconnect_count += 1
                        print(f"[VideoStream] Stream disconnected for {self.camera_id}, retrying... "
                              f"(重连次数: {self._reconnect_count})")
                        time.sleep(1.0)
                        self._ffmpeg_process.terminate()
                        time.sleep(0.5)
                        self._ffmpeg_process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,
                            bufsize=frame_size * 10,
                        )
                        continue
                
                # 重置连续超时计数
                consecutive_timeouts = 0
                
                # 转换为 numpy array (BGR 格式)
                frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((self._frame_height, self._frame_width, 3))
                
                self.frame_count += 1
                
                # 计算帧间隔
                current_time = time.time()
                if len(self._frame_intervals) > 0:
                    interval = current_time - self._last_frame_time
                    self._frame_intervals.append(interval)
                self._last_frame_time = current_time
                
                # 计算FPS和帧间隔统计
                if current_time - self.last_fps_time >= 5.0:  # 每5秒报告一次
                    self.fps = self.frame_count / 5.0
                    self.frame_count = 0
                    self.last_fps_time = current_time
                    
                    # 计算帧间隔统计
                    if len(self._frame_intervals) > 0:
                        avg_interval = sum(self._frame_intervals) / len(self._frame_intervals)
                        max_interval = max(self._frame_intervals)
                        min_interval = min(self._frame_intervals)
                        print(f"[VideoStream] camera={self.camera_id} FPS={self.fps:.1f}, "
                              f"帧间隔 avg={avg_interval*1000:.1f}ms max={max_interval*1000:.1f}ms min={min_interval*1000:.1f}ms, "
                              f"读取超时次数: {self._read_timeouts}, 重连次数: {self._reconnect_count}")
                    else:
                        print(f"[VideoStream] camera={self.camera_id} FPS={self.fps:.1f}, "
                              f"读取超时次数: {self._read_timeouts}, 重连次数: {self._reconnect_count}")
                
                # 每 detection_interval 帧执行一次检测回调
                self.detection_frame_count += 1
                if (
                    self.frame_callback
                    and self.detection_frame_count % self.detection_interval == 0
                ):
                    callback_start = time.time()
                    try:
                        print(f"[VideoStream] 触发回调 camera={self.camera_id}, 帧大小: {frame.shape}")
                        if self.async_callback and self._loop:
                            # 异步回调：在事件循环中调度
                            if self._loop.is_running():
                                asyncio.run_coroutine_threadsafe(
                                    self._async_frame_callback(frame.copy(), self.camera_id),
                                    self._loop,
                                )
                            else:
                                # 如果事件循环未运行，使用同步回调
                                print(f"[VideoStream] 警告: 事件循环未运行，使用同步回调")
                                self.frame_callback(frame.copy(), self.camera_id)
                        else:
                            # 同步回调
                            self.frame_callback(frame.copy(), self.camera_id)
                    except Exception as e:
                        print(f"[VideoStream] Frame callback error: {e}")
                    finally:
                        callback_time = (time.time() - callback_start) * 1000
                        if callback_time > 50:  # 如果回调耗时超过50ms，打印警告
                            print(f"[VideoStream] 回调耗时过长: {callback_time:.1f}ms")
                
        except Exception as e:
            print(f"[VideoStream] Error processing frames for {self.camera_id}: {e}")
        finally:
            if self._ffmpeg_process:
                try:
                    self._ffmpeg_process.terminate()
                    self._ffmpeg_process.wait(timeout=2)
                except:
                    self._ffmpeg_process.kill()

    async def _async_frame_callback(self, frame, camera_id):
        """异步帧回调包装器"""
        try:
            if asyncio.iscoroutinefunction(self.frame_callback):
                await self.frame_callback(frame, camera_id)
            else:
                self.frame_callback(frame, camera_id)
        except Exception as e:
            print(f"[VideoStream] Async frame callback error: {e}")

    def stop(self):
        """停止视频流"""
        self.running = False
        if self._ffmpeg_process:
            try:
                self._ffmpeg_process.terminate()
                self._ffmpeg_process.wait(timeout=2)
            except:
                self._ffmpeg_process.kill()
        if self.thread:
            self.thread.join(timeout=3.0)
        print(f"[VideoStream] Stopped camera {self.camera_id}")

    def get_fps(self) -> int:
        """获取当前FPS"""
        return self.fps


class StreamManager:
    """视频流管理器"""

    def __init__(self):
        self.streams: dict = {}

    def add_stream(
        self,
        camera_id: str,
        source: str,
        frame_callback: Callable,
        detection_interval: int = 5,
        async_callback: bool = False,
    ):
        """添加视频流"""
        if camera_id in self.streams:
            self.streams[camera_id].stop()

        stream = VideoStream(
            source, camera_id, frame_callback, detection_interval, async_callback
        )
        self.streams[camera_id] = stream
        return stream

    def start_stream(self, camera_id: str):
        """启动指定视频流"""
        if camera_id in self.streams:
            self.streams[camera_id].start()

    def stop_stream(self, camera_id: str):
        """停止指定视频流"""
        if camera_id in self.streams:
            self.streams[camera_id].stop()

    def stop_all(self):
        """停止所有视频流"""
        for stream in self.streams.values():
            stream.stop()
        self.streams.clear()

    def get_status(self) -> dict:
        """获取所有流状态"""
        return {
            camera_id: {"running": stream.running, "fps": stream.fps}
            for camera_id, stream in self.streams.items()
        }


# 全局视频流管理器实例
stream_manager = StreamManager()
