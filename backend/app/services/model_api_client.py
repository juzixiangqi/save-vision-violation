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
        imgsz = imgsz or self.config.imgsz
        conf = conf or self.config.confidence

        try:
            # 编码图像为JPEG
            _, img_encoded = cv2.imencode(".jpg", frame)
            if not _:
                print("[ModelAPIClient] 图像编码失败")
                return []

            # 准备multipart数据
            files = {
                "file": ("image.jpg", io.BytesIO(img_encoded.tobytes()), "image/jpeg")
            }
            data = {
                "imgsz": str(imgsz),
                "conf": str(conf),
            }

            # 发送请求
            response = self.session.post(
                self.config.url,
                files=files,
                data=data,
                timeout=self.config.timeout,
            )
            response.raise_for_status()

            # 解析响应
            result = response.json()
            if result.get("status") != "success":
                print(f"[ModelAPIClient] API返回错误: {result}")
                return []

            # 转换为Detection对象
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

            return detections

        except requests.exceptions.ConnectionError as e:
            print(f"[ModelAPIClient] 连接错误: {e}")
            return []
        except requests.exceptions.Timeout as e:
            print(f"[ModelAPIClient] 请求超时: {e}")
            return []
        except Exception as e:
            print(f"[ModelAPIClient] 检测错误: {e}")
            return []

    def health_check(self) -> bool:
        """检查API服务是否可用"""
        try:
            response = self.session.get(
                self.config.url.replace("/predict", "/health"),
                timeout=5,
            )
            return response.status_code == 200
        except:
            return False
