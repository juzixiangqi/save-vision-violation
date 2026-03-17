#!/usr/bin/env python3
"""
模型文件下载脚本
自动下载 YOLOv8 检测模型和姿态估计模型
"""

import os
import urllib.request
from pathlib import Path


def download_file(url: str, dest_path: str):
    """下载文件并显示进度"""
    print(f"Downloading: {os.path.basename(dest_path)}")
    print(f"From: {url}")

    def progress_hook(count, block_size, total_size):
        percent = int(count * block_size * 100 / total_size)
        print(f"\rProgress: {percent}%", end="", flush=True)

    urllib.request.urlretrieve(url, dest_path, progress_hook)
    print("\nDone!")


def main():
    # 模型目录
    backend_dir = Path(__file__).parent / "backend"
    backend_dir.mkdir(exist_ok=True)

    # 模型配置
    models = [
        {
            "name": "yolov8n.pt",
            "url": "https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8n.pt",
            "desc": "YOLOv8 Nano 目标检测模型",
        },
        {
            "name": "yolov8n-pose.pt",
            "url": "https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8n-pose.pt",
            "desc": "YOLOv8 Nano 姿态估计模型",
        },
    ]

    print("=" * 60)
    print("仓库违规检测系统 - 模型下载")
    print("=" * 60)

    for model in models:
        model_path = backend_dir / model["name"]

        if model_path.exists():
            print(f"\n✓ {model['name']} 已存在，跳过下载")
            continue

        print(f"\n{model['desc']}")
        print("-" * 60)

        try:
            download_file(model["url"], str(model_path))
        except Exception as e:
            print(f"✗ 下载失败: {e}")
            print(f"请手动下载: {model['url']}")
            print(f"保存到: {model_path}")

    print("\n" + "=" * 60)
    print("模型下载完成！")
    print("=" * 60)
    print("\n你现在可以启动后端服务了：")
    print("  cd backend")
    print("  uv run python run.py")


if __name__ == "__main__":
    main()
