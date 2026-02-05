"""FastAPI主入口"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import sys

from .config import get_settings
from .edge_manager import edge_manager
from .routers import chat_router
from .models import HealthResponse


# 日志配置
logger.remove()
logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}")
logger.add("logs/api_{time}.log", rotation="100 MB", retention="7 days")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("启动API服务...")
    
    # 尝试连接到Edge
    connected = await edge_manager.connect_to_edge(max_retries=3)
    if connected:
        logger.info("✓ 已连接到Edge浏览器")
    else:
        logger.warning("✗ 未连接到Edge，请先运行: python -m app.edge_manager start")
    
    yield
    
    logger.info("关闭API服务...")
    await edge_manager.disconnect()


app = FastAPI(
    title="内部AI工具API",
    description="企业环境 - 长驻Edge进程方案",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="healthy" if edge_manager.is_connected else "disconnected",
        edge_connected=edge_manager.is_connected,
        session_count=edge_manager.session_count
    )


@app.get("/")
async def root():
    return {
        "name": "内部AI工具API",
        "version": "2.0.0",
        "edge_connected": edge_manager.is_connected,
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=True)
