"""AI狼人杀后端应用配置"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置，从环境变量或 .env 文件读取"""

    # 应用基础
    app_name: str = "AI狼人杀"
    debug: bool = False

    # MySQL 数据库
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "ai_werewolf"

    # CORS
    cors_origins: list[str] = ["http://localhost:3003", "http://localhost:5173", "http://localhost:3000"]

    # 游戏数据目录
    game_data_dir: str = "game_data"

    # JWT 认证
    jwt_secret: str = "ai-werewolf-secret-change-me-in-production"
    jwt_expire_hours: int = 72

    @property
    def database_url(self) -> str:
        from urllib.parse import quote_plus
        password = quote_plus(self.db_password) if self.db_password else ""
        return (
            f"mysql+aiomysql://{self.db_user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    model_config = {"env_file": ".env", "env_prefix": "WEREWOLF_"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
