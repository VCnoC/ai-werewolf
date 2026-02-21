"""LLM 配置表模型"""

from datetime import datetime

from sqlalchemy import String, Text, DateTime, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class LLMConfig(Base):
    """LLM 配置表：存储用户配置的各种大模型接入信息"""

    __tablename__ = "llm_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), comment="配置名称")
    api_url: Mapped[str] = mapped_column(String(500), comment="API 地址")
    api_key: Mapped[str] = mapped_column(Text, comment="API Key（加密存储）")
    model_name: Mapped[str] = mapped_column(String(200), comment="模型名称")
    append_chat_path: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1",
        comment="是否自动拼接 /chat/completions"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
