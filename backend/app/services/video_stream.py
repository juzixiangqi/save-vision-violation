import cv2
import numpy as np
import threading
import time
from typing import Callable, Optional
from datetime import datetime


class VideoStream:
    """视频流处理器"""

    def __init__(
        self, source: str, camera_id: str, frame_callback: Optional[Callable] = None
    ):
        self.source = source
        self.camera_id = camera_id
        self.frame_callback = frame_callback
        self.cap = None
        self.running = False
        self.thread = None
        self.fps = 0
        self.frame_count = 0
        self.last_fps_time = time.time()

    def start(self):
        """启动视频流"""
        self.cap = cv2.VideoCapture(self.source)
        if not self.cap.isOpened():
            raise Exception(f"Cannot open video source: {self.source}")

        self.running = True
        self.thread = threading.Thread(target=self._process_frames)
        self.thread.start()
        print(f"[VideoStream] Started camera {self.camera_id}")

    def _process_frames(self):
        """处理视频帧"""
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                # 视频结束或读取失败，循环播放（本地视频）
                if isinstance(self.source, str) and self.source.endswith(
                    (".mp4", ".avi", ".mkv")
                ):
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    time.sleep(0.1)
                    continue

            self.frame_count += 1

            # 计算FPS
            current_time = time.time()
            if current_time - self.last_fps_time >= 1.0:
                self.fps = self.frame_count
                self.frame_count = 0
                self.last_fps_time = current_time

            # 回调处理
            if self.frame_callback:
                try:
                    self.frame_callback(frame, self.camera_id)
                except Exception as e:
                    print(f"[VideoStream] Frame callback error: {e}")

            # 控制帧率
            time.sleep(0.033)  # ~30fps

    def stop(self):
        """停止视频流"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.cap:
            self.cap.release()
        print(f"[VideoStream] Stopped camera {self.camera_id}")

    def get_fps(self) -> int:
        """获取当前FPS"""
        return self.fps


class StreamManager:
    """视频流管理器"""

    def __init__(self):
        self.streams: dict = {}

    def add_stream(self, camera_id: str, source: str, frame_callback: Callable):
        """添加视频流"""
        if camera_id in self.streams:
            self.streams[camera_id].stop()

        stream = VideoStream(source, camera_id, frame_callback)
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
