"""异步检测处理器 - 处理API调用超时和并发控制"""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Any
import numpy as np

from app.core.detector import YOLODetector, Detection


@dataclass
class FrameTask:
    """帧处理任务"""

    frame: np.ndarray
    timestamp: float
    frame_number: int
    camera_id: str
    result: Optional[List[Detection]] = None
    completed: bool = False


class AsyncDetector:
    """异步检测处理器

    特性：
    - API超时保护（默认250ms）
    - 并发请求控制（最多4个pending）
    - 结果缓存（超时或失败时使用上一次成功结果）
    - 帧间隔异常检测（RTSP卡顿保护）
    - 使用信号量控制并发，避免任务堆积

    注意：本类不负责节流控制，调用频率由 VideoStream.detection_interval 统一管理
    """

    def __init__(
        self,
        detector: YOLODetector,
        api_timeout: float = 0.25,  # 250ms超时
        max_pending: int = 4,  # 最多4个并发请求
        max_queue_size: int = 6,  # 保留最近6帧
    ):
        self.detector = detector
        self.api_timeout = api_timeout
        self.max_pending = max_pending
        self.max_queue_size = max_queue_size
        print(
            f"[AsyncDetector] Initialized with api_timeout={api_timeout}s ({api_timeout * 1000:.0f}ms), max_pending={max_pending}"
        )

        # 状态
        self.frame_counter = 0
        self.frame_queue = deque(maxlen=max_queue_size)
        self.last_result: Optional[List[Detection]] = None
        self.last_success_time = 0
        self._last_frame_time = 0.0

        # 使用信号量控制并发
        self._semaphore = asyncio.Semaphore(max_pending)

        # 活跃任务计数（用于监控）
        self._active_tasks = 0
        self._lock = asyncio.Lock()

        # 统计
        self.stats = {
            "total_frames": 0,
            "processed_frames": 0,
            "timeout_count": 0,
            "error_count": 0,
            "success_count": 0,
            "skipped_count": 0,  # 新增：跳过的帧数
            "avg_latency": 0.0,
        }

    def on_frame(
        self, frame: np.ndarray, camera_id: str = ""
    ) -> Optional[List[Detection]]:
        """执行异步检测 - 每次调用都会触发检测（带超时保护）

        注意：调用频率由 VideoStream.detection_interval 控制，本方法不做额外节流

        Args:
            frame: 视频帧
            camera_id: 摄像头ID

        Returns:
            当前可用的检测结果（可能是上一帧的缓存）
        """
        self.frame_counter += 1
        current_time = time.time()

        # 检查帧间隔异常（RTSP卡顿保护）
        if self._last_frame_time > 0:
            interval = current_time - self._last_frame_time
            if interval > 0.5:  # 超过500ms说明卡顿
                print(f"[AsyncDetector] 帧间隔异常: {interval:.3f}s，重置计数器")
                self.frame_counter = 0
        self._last_frame_time = current_time

        self.stats["total_frames"] += 1

        # 添加到队列
        task = FrameTask(
            frame=frame,
            timestamp=current_time,
            frame_number=self.frame_counter,
            camera_id=camera_id,
        )
        self.frame_queue.append(task)

        # 检查当前活跃任务数
        if self._active_tasks >= self.max_pending:
            # 并发已满，跳过当前帧
            self.stats["skipped_count"] += 1
            print(
                f"[AsyncDetector] 跳过帧 #{task.frame_number}，"
                f"当前活跃任务 {self._active_tasks}/{self.max_pending}"
            )
            return self.last_result

        # 发起异步检测
        asyncio.create_task(self._detect_async(task))

        # 返回当前可用的最新结果
        return self.last_result

    async def _detect_async(self, task: FrameTask):
        """执行异步检测（带超时）"""
        async with self._semaphore:
            # 增加活跃任务计数
            async with self._lock:
                self._active_tasks += 1

            start_time = time.time()

            # 记录进入时的时间戳和等待时间
            queue_wait_time = (start_time - task.timestamp) * 1000
            thread_pool_submit_time = 0
            api_time = 0

            try:
                # 在线程池中执行同步的检测（避免阻塞事件循环）
                loop = asyncio.get_event_loop()
                thread_pool_submit_start = time.time()

                detect_task = loop.run_in_executor(
                    None,  # 使用默认线程池
                    self.detector.detect,
                    task.frame,
                )

                # 提交到线程池的时间
                thread_pool_submit_time = (
                    time.time() - thread_pool_submit_start
                ) * 1000

                # 等待结果（带超时）
                api_start = time.time()
                result = await asyncio.wait_for(detect_task, timeout=self.api_timeout)
                api_time = (time.time() - api_start) * 1000

                # 成功
                task.result = result
                task.completed = True
                self.last_result = result
                self.last_success_time = time.time()
                self.stats["success_count"] += 1

                total_latency = time.time() - start_time
                self._update_avg_latency(total_latency)

                # 每帧都打印详细日志（方便分析性能瓶颈）
                print(
                    f"[AsyncDetector] 检测成功 #{task.frame_number}, "
                    f"总延迟: {total_latency * 1000:.1f}ms "
                    f"(队列等待:{queue_wait_time:.1f}ms "
                    f"线程池提交:{thread_pool_submit_time:.1f}ms "
                    f"API调用:{api_time:.1f}ms), "
                    f"检测到{len(result) if result else 0}个目标, "
                    f"累计: 成功{self.stats['success_count']}/"
                    f"超时{self.stats['timeout_count']}/"
                    f"跳过{self.stats['skipped_count']}/"
                    f"错误{self.stats['error_count']}"
                )

            except asyncio.TimeoutError:
                task.completed = True
                task.result = self.last_result  # 使用缓存结果
                self.stats["timeout_count"] += 1
                total_time = (time.time() - start_time) * 1000
                print(
                    f"[AsyncDetector] 检测超时 #{task.frame_number} "
                    f"总耗时:{total_time:.1f}ms (限制:{self.api_timeout * 1000:.0f}ms) "
                    f"队列等待:{queue_wait_time:.1f}ms, "
                    f"使用缓存结果 ({len(self.last_result) if self.last_result else 0}个目标)"
                )

            except Exception as e:
                task.completed = True
                task.result = self.last_result  # 使用缓存结果
                self.stats["error_count"] += 1
                total_time = (time.time() - start_time) * 1000
                print(
                    f"[AsyncDetector] 检测错误 #{task.frame_number} ({total_time:.1f}ms): {e}"
                )

            finally:
                # 减少活跃任务计数
                async with self._lock:
                    self._active_tasks -= 1

    def _update_avg_latency(self, latency: float):
        """更新平均延迟"""
        n = self.stats["success_count"]
        self.stats["avg_latency"] = (self.stats["avg_latency"] * (n - 1) + latency) / n

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            **self.stats,
            "active_tasks": self._active_tasks,
            "queue_size": len(self.frame_queue),
            "last_result_age": time.time() - self.last_success_time
            if self.last_success_time
            else -1,
        }

    def reset(self):
        """重置状态"""
        self.frame_counter = 0
        self.frame_queue.clear()
        self.last_result = None
        self.last_success_time = 0
        self._last_frame_time = 0.0
        self._active_tasks = 0
        self.stats = {
            "total_frames": 0,
            "processed_frames": 0,
            "timeout_count": 0,
            "error_count": 0,
            "success_count": 0,
            "skipped_count": 0,
            "avg_latency": 0.0,
        }
