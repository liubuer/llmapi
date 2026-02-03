"""
FastAPI主入口
内部AI工具API包装器
"""
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from .config import get_settings
from .browser_manager import browser_manager
from .routers import chat_router
from .models import HealthResponse, ErrorResponse, ErrorDetail


# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)
logger.add(
    "logs/api_{time}.log",
    rotation="500 MB",
    retention="7 days",
    level="DEBUG"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("正在启动内部AI工具API服务...")
    await browser_manager.start()
    logger.info("服务启动完成")
    
    yield
    
    # 关闭时
    logger.info("正在关闭服务...")
    await browser_manager.stop()
    logger.info("服务已关闭")


# 创建FastAPI应用
app = FastAPI(
    title="内部AI工具API",
    description="将公司内部网页版AI工具包装成OpenAI兼容的API接口",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 注册路由
app.include_router(chat_router)


# 健康检查
@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """健康检查端点"""
    return HealthResponse(
        status="healthy",
        browser_sessions=browser_manager.session_count,
        available_sessions=browser_manager.available_session_count
    )


# 根路径
@app.get("/", tags=["Root"])
async def root():
    """根路径"""
    return {
        "name": "内部AI工具API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }


# 会话信息
@app.get("/sessions", tags=["Admin"])
async def get_sessions():
    """获取当前会话信息"""
    return {
        "total_sessions": browser_manager.session_count,
        "available_sessions": browser_manager.available_session_count,
        "max_sessions": get_settings().max_sessions,
        "sessions": browser_manager.get_session_info()
    }


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    logger.exception(f"未处理的异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": f"内部服务器错误: {str(exc)}",
                "type": "internal_error",
                "code": "internal_error"
            }
        }
    )


# 启动脚本
if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level="info"
    )
