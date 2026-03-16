from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import config, zones, rules

app = FastAPI(title="仓库违规检测系统", version="1.0.0")

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


@app.get("/")
async def root():
    return {"message": "仓库违规检测系统API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
