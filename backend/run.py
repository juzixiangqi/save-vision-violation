#!/usr/bin/env python3
"""
仓库违规检测系统启动脚本
"""

import uvicorn
import os
import sys


def main():
    """主函数"""
    # 确保工作目录正确
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # 启动FastAPI服务
    uvicorn.run(
        "app.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info"
    )


if __name__ == "__main__":
    main()
