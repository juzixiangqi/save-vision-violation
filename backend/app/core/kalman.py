import numpy as np
from filterpy.kalman import KalmanFilter
from typing import Tuple


class BoxKalmanFilter:
    """用于箱子跟踪的卡尔曼滤波器"""

    def __init__(self):
        # 状态: [x, y, vx, vy]
        # 观测: [x, y]
        self.kf = KalmanFilter(dim_x=4, dim_z=2)

        # 状态转移矩阵
        self.kf.F = np.array([[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]])

        # 观测矩阵
        self.kf.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])

        # 观测噪声
        self.kf.R *= 10

        # 初始协方差
        self.kf.P *= 100

        # 过程噪声
        self.kf.Q *= 0.1

        self.initialized = False

    def init(self, x: float, y: float):
        """初始化滤波器"""
        self.kf.x = np.array([x, y, 0, 0])
        self.initialized = True

    def predict(self) -> Tuple[float, float]:
        """预测下一状态"""
        if not self.initialized:
            return (0, 0)
        self.kf.predict()
        return (self.kf.x[0], self.kf.x[1])

    def update(self, x: float, y: float):
        """更新状态"""
        if not self.initialized:
            self.init(x, y)
        else:
            self.kf.update(np.array([x, y]))

    def get_position(self) -> Tuple[float, float]:
        """获取当前位置"""
        return (self.kf.x[0], self.kf.x[1])

    def get_velocity(self) -> Tuple[float, float]:
        """获取当前速度"""
        return (self.kf.x[2], self.kf.x[3])
