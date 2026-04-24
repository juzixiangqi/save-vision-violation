import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import config, zones, rules, monitor, debug_stream
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print("[Main] Starting up...")
    yield
    # 关闭时
    print("[Main] Shutting down...")
    from app.services.video_stream import stream_manager
    from app.services.rabbitmq_client import rabbitmq_client

    stream_manager.stop_all()
    rabbitmq_client.close()


app = FastAPI(title="仓库违规检测系统", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(config.router)
app.include_router(zones.router)
app.include_router(rules.router)
app.include_router(monitor.router)
app.include_router(debug_stream.router)


@app.get("/")
async def root():
    return {"message": "仓库违规检测系统API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "api_mode": True,
        "model_api_url": os.getenv(
            "MODEL_API_URL", "http://10.190.28.23:31674/predict"
        ),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
