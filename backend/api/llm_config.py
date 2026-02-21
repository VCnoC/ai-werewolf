"""LLM 配置 CRUD API"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.llm_config import LLMConfig
from models.user import User
from utils import encrypt_key, decrypt_key
from auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm-configs", tags=["LLM配置"])


# --- Pydantic Schemas ---

class LLMConfigCreate(BaseModel):
    name: str
    api_url: str
    api_key: str
    model_name: str
    append_chat_path: bool = True


class LLMConfigUpdate(BaseModel):
    name: str | None = None
    api_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    append_chat_path: bool | None = None


class LLMConfigResponse(BaseModel):
    id: int
    name: str
    api_url: str
    api_key_masked: str
    model_name: str
    append_chat_path: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def mask_key(plain_key: str) -> str:
    """遮蔽 API Key，仅显示前4位和后4位"""
    if len(plain_key) <= 8:
        return "****"
    return f"{plain_key[:4]}****{plain_key[-4:]}"


def to_response(config: LLMConfig) -> LLMConfigResponse:
    try:
        plain_key = decrypt_key(config.api_key)
    except Exception:
        plain_key = config.api_key  # 兼容未加密的旧数据
    return LLMConfigResponse(
        id=config.id,
        name=config.name,
        api_url=config.api_url,
        api_key_masked=mask_key(plain_key),
        model_name=config.model_name,
        append_chat_path=config.append_chat_path if config.append_chat_path is not None else True,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def get_decrypted_key(config: LLMConfig) -> str:
    """获取解密后的 API Key"""
    try:
        return decrypt_key(config.api_key)
    except Exception:
        return config.api_key  # 兼容未加密的旧数据


# --- API Endpoints ---

@router.get("", response_model=list[LLMConfigResponse])
async def list_configs(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    """获取所有 LLM 配置"""
    result = await db.execute(select(LLMConfig).order_by(LLMConfig.id))
    return [to_response(c) for c in result.scalars().all()]


@router.post("", response_model=LLMConfigResponse, status_code=201)
async def create_config(data: LLMConfigCreate, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    """创建新 LLM 配置"""
    config_data = data.model_dump()
    config_data["api_key"] = encrypt_key(config_data["api_key"])
    config = LLMConfig(**config_data)
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return to_response(config)


@router.put("/{config_id}", response_model=LLMConfigResponse)
async def update_config(
    config_id: int, data: LLMConfigUpdate, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)
):
    """更新 LLM 配置"""
    config = await db.get(LLMConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    update_data = data.model_dump(exclude_unset=True)
    # 加密新的 API Key
    if "api_key" in update_data and update_data["api_key"]:
        update_data["api_key"] = encrypt_key(update_data["api_key"])
    elif "api_key" in update_data:
        # 空字符串表示不修改，移除该字段
        del update_data["api_key"]
    for key, value in update_data.items():
        setattr(config, key, value)
    await db.commit()
    await db.refresh(config)
    return to_response(config)


@router.delete("/{config_id}", status_code=204)
async def delete_config(config_id: int, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    """删除 LLM 配置"""
    config = await db.get(LLMConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    await db.delete(config)
    await db.commit()


@router.post("/{config_id}/test")
async def test_config(config_id: int, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    """测试 LLM 配置连通性"""
    config = await db.get(LLMConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    try:
        import httpx

        plain_key = get_decrypted_key(config)
        base_url = config.api_url.rstrip("/")
        url = f"{base_url}/chat/completions" if config.append_chat_path else base_url
        headers = {
            "Authorization": f"Bearer {plain_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config.model_name,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
        }
        async with httpx.AsyncClient(timeout=30) as http_client:
            resp = await http_client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return {"success": True, "message": f"连接成功，模型响应: {content}"}
    except Exception as e:
        logger.warning(f"LLM 配置测试失败 (id={config_id}): {e}")
        return {"success": False, "message": "连接失败，请检查 API 地址、Key 和模型名称是否正确"}
