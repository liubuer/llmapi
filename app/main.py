"""FastAPIメインエントリーポイント"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import sys

from .config import get_settings
from .edge_manager import edge_manager
from .routers import chat_router
from .models import HealthResponse


# ログ設定
logger.remove()
logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}")
logger.add("logs/api_{time}.log", rotation="100 MB", retention="7 days")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("APIサービスを起動中...")

    # Edgeへの接続を試行
    connected = await edge_manager.connect_to_edge(max_retries=3)
    if connected:
        logger.info("✓ Edgeブラウザに接続完了")
    else:
        logger.warning("✗ Edge未接続。先に実行してください: python -m app.edge_manager start")

    yield

    logger.info("APIサービスを終了中...")
    await edge_manager.disconnect()


app = FastAPI(
    title="社内AIツールAPI",
    description="エンタープライズ環境 - 常駐Edgeプロセス方式",
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
        "name": "社内AIツールAPI",
        "version": "2.0.0",
        "edge_connected": edge_manager.is_connected,
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=True)
