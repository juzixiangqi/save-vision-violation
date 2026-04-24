FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装uv
RUN pip install --no-cache-dir uv

# 复制依赖文件
COPY pyproject.toml .
COPY README.md .

# 创建虚拟环境并安装依赖
RUN uv venv && uv sync

# 复制应用代码
COPY backend/app ./app
COPY backend/config.yml .
COPY backend/run.py .

# 暴露端口
EXPOSE 8000

# 设置环境变量
ENV PYTHONPATH=/app
ENV MODEL_API_URL=http://10.190.28.23:31674/predict
ENV MODEL_API_TIMEOUT=30
ENV MODEL_API_IMGSZ=640
ENV MODEL_API_CONFIDENCE=0.2

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# 启动命令
CMD ["uv", "run", "python", "run.py"]
