"""MySQL 数据库连接与 ORM 基础配置"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_recycle=300,    # 5分钟回收空闲连接，避免 MySQL wait_timeout 断开
    pool_pre_ping=True,  # 每次使用前检测连接是否存活，死连接自动重连
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """ORM 基类"""
    pass


async def init_db():
    """初始化数据库（创建所有表）"""
    # 确保所有模型已注册到 Base.metadata
    import models.llm_config  # noqa: F401
    import models.game_models  # noqa: F401
    import models.user  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """获取数据库会话（FastAPI 依赖注入用）"""
    async with async_session() as session:
        yield session
