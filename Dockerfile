FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# 配置内网 apt 源
RUN rm -f /etc/apt/sources.list && cat > /etc/apt/sources.list << 'EOF'
# lzkj local apt mirror of tencent
deb https://lxkjyum.luxsan-ict.com/repository/apt-proxy-tencent/ubuntu jammy main restricted universe multiverse
deb https://lxkjyum.luxsan-ict.com/repository/apt-proxy-tencent/ubuntu jammy-updates main restricted universe multiverse
deb https://lxkjyum.luxsan-ict.com/repository/apt-proxy-tencent/ubuntu jammy-backports main restricted universe multiverse
deb https://lxkjyum.luxsan-ict.com/repository/apt-proxy-tencent/ubuntu jammy-security main restricted universe multiverse
# lzkj local apt mirror of aliyun
deb https://lxkjyum.luxsan-ict.com/repository/apt-proxy-aliyun/ubuntu jammy main restricted universe multiverse
deb https://lxkjyum.luxsan-ict.com/repository/apt-proxy-aliyun/ubuntu jammy-updates main restricted universe multiverse
deb https://lxkjyum.luxsan-ict.com/repository/apt-proxy-aliyun/ubuntu jammy-backports main restricted universe multiverse
deb https://lxkjyum.luxsan-ict.com/repository/apt-proxy-aliyun/ubuntu jammy-security main restricted universe multiverse
EOF

# 安装 Python 3.10 和系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    python3-venv \
    python3.10-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 创建 python 符号链接
RUN ln -sf /usr/bin/python3.10 /usr/bin/python

# 配置 pip 使用内网 PyPI 源
RUN pip config set global.index-url https://lxkjyum.luxsan-ict.com/repository/lzpypi/simple

WORKDIR /app

# 安装 uv
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

# 设置环境变量（运行时通过 -e 覆盖）
ENV PYTHONPATH=/app
ENV MODEL_API_URL=http://localhost:31674/predict
ENV MODEL_API_TIMEOUT=30
ENV MODEL_API_IMGSZ=640
ENV MODEL_API_CONFIDENCE=0.2

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uv", "run", "python", "run.py"]
