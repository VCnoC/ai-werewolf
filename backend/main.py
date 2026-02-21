"""AI狼人杀 - FastAPI 应用入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import init_db
from api.llm_config import router as llm_config_router
from api.game import router as game_router
from api.websocket import router as ws_router
from api.auth import router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    try:
        await init_db()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"数据库初始化失败，稍后重试: {e}")
    yield


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "app": settings.app_name}


# 注册路由
app.include_router(auth_router)
app.include_router(llm_config_router)
app.include_router(game_router)
app.include_router(ws_router)
