import io
import os
from typing import List, Optional

import cv2
import numpy as np
import requests

from app.config.models import ModelAPIConfig
from app.core.detector import Detection


class ModelAPIClient:
    """模型API客户端 - 通过HTTP调用远程模型服务"""

    def __init__(self, config: Optional[ModelAPIConfig] = None):
        if config is None:
            # 从环境变量读取配置
            config = ModelAPIConfig(
                url=os.getenv("MODEL_API_URL", "http://10.190.28.23:31674/predict"),
                timeout=int(os.getenv("MODEL_API_TIMEOUT", "30")),
                imgsz=int(os.getenv("MODEL_API_IMGSZ", "640")),
                confidence=float(os.getenv("MODEL_API_CONFIDENCE", "0.2")),
            )
        self.config = config
        self.session = requests.Session()

    def detect(
        self,
        frame: np.ndarray,
        imgsz: Optional[int] = None,
        conf: Optional[float] = None,
    ) -> List[Detection]:
        """
        通过API检测图像

        Args:
            frame: OpenCV图像 (BGR格式)
            imgsz: 输入尺寸（覆盖配置）
            conf: 置信度阈值（覆盖配置）

        Returns:
            Detection对象列表
        """
        import time

        total_start = time.time()
        imgsz = imgsz or self.config.imgsz
        conf = conf or self.config.confidence

        try:
            # 1. 编码图像为JPEG
            encode_start = time.time()
            _, img_encoded = cv2.imencode(".jpg", frame)
            encode_time = (time.time() - encode_start) * 1000
            if not _:
                print("[ModelAPIClient] 图像编码失败")
                return []

            # 2. 准备multipart数据
            prepare_start = time.time()
            files = {
                "file": ("image.jpg", io.BytesIO(img_encoded.tobytes()), "image/jpeg")
            }
            data = {
                "imgsz": str(imgsz),
                "conf": str(conf),
            }
            prepare_time = (time.time() - prepare_start) * 1000

            # 3. 发送请求
            request_start = time.time()
            img_size_kb = len(img_encoded.tobytes()) / 1024
            print(f"[ModelAPIClient] 开始发送HTTP请求，目标URL: {self.config.url}, 图片: {img_size_kb:.1f}KB, timeout={self.config.timeout}s")
            
            response = self.session.post(
                self.config.url,
                files=files,
                data=data,
                timeout=self.config.timeout,
            )
            request_time = (time.time() - request_start) * 1000
            
            print(f"[ModelAPIClient] HTTP请求完成，状态码: {response.status_code}, 耗时: {request_time:.1f}ms")
            response.raise_for_status()

            # 4. 解析响应
            parse_start = time.time()
            result = response.json()
            parse_time = (time.time() - parse_start) * 1000

            if result.get("status") != "success":
                print(f"[ModelAPIClient] API返回错误: {result}")
                return []

            # 5. 转换为Detection对象
            convert_start = time.time()
            detections = []
            for i, pred in enumerate(result.get("predictions", [])):
                bbox = pred["bbox"]
                x1, y1, x2, y2 = bbox
                center = ((x1 + x2) / 2, (y1 + y2) / 2)
                bottom_center = ((x1 + x2) / 2, y2)

                detections.append(
                    Detection(
                        id=f"person_carry_{i + 1}",
                        bbox=[float(x) for x in bbox],
                        confidence=float(pred["confidence"]),
                        center=center,
                        bottom_center=bottom_center,
                        class_id=int(pred.get("class_idx", 0)),
                        class_name=str(pred.get("class", "person_carry")),
                    )
                )
            convert_time = (time.time() - convert_start) * 1000

            total_time = (time.time() - total_start) * 1000
            print(
                f"[ModelAPIClient] 检测耗时: {total_time:.1f}ms "
                f"(编码:{encode_time:.1f}ms 准备:{prepare_time:.1f}ms "
                f"请求:{request_time:.1f}ms 解析:{parse_time:.1f}ms "
                f"转换:{convert_time:.1f}ms) "
                f"图片:{frame.shape[1]}x{frame.shape[0]}({img_size_kb:.1f}KB) "
                f"检测到{len(detections)}个目标"
            )

            return detections

        except requests.exceptions.ConnectionError as e:
            total_time = (time.time() - total_start) * 1000
            print(f"[ModelAPIClient] 连接错误 ({total_time:.1f}ms): {e}")
            print(f"[ModelAPIClient] 诊断: 无法连接到 {self.config.url}，请检查网络或服务器状态")
            return []
        except requests.exceptions.Timeout as e:
            total_time = (time.time() - total_start) * 1000
            print(f"[ModelAPIClient] 请求超时 ({total_time:.1f}ms): {e}")
            print(f"[ModelAPIClient] 诊断: requests.timeout={self.config.timeout}s，但请求耗时{total_time:.1f}ms，可能图片太大或网络慢")
            return []
        except requests.exceptions.JSONDecodeError as e:
            total_time = (time.time() - total_start) * 1000
            print(f"[ModelAPIClient] JSON解析错误 ({total_time:.1f}ms): {e}")
            return []
        except Exception as e:
            total_time = (time.time() - total_start) * 1000
            print(f"[ModelAPIClient] 检测错误 ({total_time:.1f}ms): {e}")
            import traceback
            traceback.print_exc()
            return []

    def health_check(self) -> bool:
        """检查API服务是否可用"""
        try:
            from urllib.parse import urljoin, urlparse

            parsed = urlparse(self.config.url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            health_url = urljoin(base_url, "/health")

            response = self.session.get(health_url, timeout=5)
            return response.status_code == 200
        except Exception:
            return False
