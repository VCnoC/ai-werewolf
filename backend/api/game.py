"""游戏控制 API"""

import asyncio
import json
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db
from models.llm_config import LLMConfig
from game.state import GameState
from game.engine import GameEngine
from models.user import User
from auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/games", tags=["游戏"])

# 内存中的游戏实例（单实例支持1局）
_active_games: dict[str, GameState] = {}
_active_engines: dict[str, GameEngine] = {}


def get_engine(game_id: str) -> GameEngine | None:
    """获取运行中的游戏引擎实例（供 WebSocket 模块调用）"""
    return _active_engines.get(game_id)


class GameCreateRequest(BaseModel):
    player_configs: list[int]  # 12个 LLM 配置 ID

    @field_validator("player_configs")
    @classmethod
    def validate_player_count(cls, v: list[int]) -> list[int]:
        if len(v) != 12:
            raise ValueError("需要12个 LLM 配置")
        return v


class GameCreateResponse(BaseModel):
    game_id: str


@router.post("", response_model=GameCreateResponse, status_code=201)
async def create_game(data: GameCreateRequest, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    """创建游戏（传入12个AI的LLM配置ID，随机分配角色）"""
    # 验证所有配置ID存在
    result = await db.execute(
        select(LLMConfig.id).where(LLMConfig.id.in_(data.player_configs))
    )
    existing_ids = set(result.scalars().all())
    missing = set(data.player_configs) - existing_ids
    if missing:
        raise HTTPException(status_code=400, detail=f"LLM 配置不存在: {missing}")

    # 生成唯一 game_id（碰撞检测）
    settings = get_settings()
    for _ in range(10):
        game_id = str(uuid.uuid4())[:8]
        game_dir = os.path.join(settings.game_data_dir, f"game_{game_id}")
        if game_id not in _active_games and not os.path.exists(game_dir):
            break
    else:
        game_id = str(uuid.uuid4())  # 兜底使用完整 UUID

    state = GameState.create(game_id, data.player_configs)
    state.save()
    _active_games[game_id] = state

    # 不返回角色分配信息（上帝视角通过观战页面查看）
    return GameCreateResponse(game_id=game_id)


@router.post("/{game_id}/start")
async def start_game(game_id: str, _user: User = Depends(get_current_user)):
    """开始游戏（启动游戏引擎后台任务）"""
    state = _active_games.get(game_id)
    if not state:
        state = GameState.load(game_id)
        if not state:
            raise HTTPException(status_code=404, detail="游戏不存在")
        _active_games[game_id] = state

    if state.status == "running":
        raise HTTPException(status_code=400, detail="游戏已在运行中")
    if state.status == "ended":
        raise HTTPException(status_code=400, detail="游戏已结束，无法重新开始")
    if game_id in _active_engines:
        raise HTTPException(status_code=400, detail="游戏引擎已在运行中")

    # 原子化设置运行态，防止并发重复启动
    state.status = "running"
    state.save()

    # 创建事件回调（WebSocket 广播）
    from api.websocket import make_event_callback, init_event_buffer
    init_event_buffer(game_id)
    event_callback = make_event_callback(game_id)

    # 创建游戏引擎
    engine = GameEngine(state, event_callback)
    _active_engines[game_id] = engine

    # 后台启动游戏循环
    async def _run_game():
        try:
            from ai.agent import AIAgent
            ai_agent = AIAgent(state)
            engine.ai = ai_agent
            await engine.run()
        except Exception as e:
            logger.error(f"游戏 {game_id} 运行异常: {e}", exc_info=True)
            await event_callback({
                "type": "game.error",
                "data": {"message": f"游戏异常: {e}"},
            })
        finally:
            _active_engines.pop(game_id, None)
            _active_games.pop(game_id, None)
            # 延迟清理事件缓冲（给客户端重连的时间）
            async def _delayed_cleanup():
                await asyncio.sleep(60)
                from api.websocket import cleanup_event_buffer
                cleanup_event_buffer(game_id)
            asyncio.create_task(_delayed_cleanup())

    asyncio.create_task(_run_game())

    return {"status": "started", "game_id": game_id}


@router.get("/{game_id}/state")
async def get_game_state(game_id: str):
    """获取游戏当前状态（上帝视角，包含角色信息）"""
    state = _active_games.get(game_id)
    if not state:
        state = GameState.load(game_id)
        if not state:
            raise HTTPException(status_code=404, detail="游戏不存在")

    response = {
        "game_id": state.game_id,
        "status": state.status,
        "current_round": state.current_round,
        "current_phase": state.current_phase.value,
        "alive_players": state.get_alive_ids(),
        "dead_players": [
            {"player_id": d.player_id, "round": d.round, "cause": d.cause.value}
            for d in state.dead_players
        ],
        "sheriff": state.sheriff_id,
        "winner": state.winner,
        "players": {
            str(pid): {
                "role": p.role.value,
                "faction": p.faction.value,
                "is_alive": p.is_alive,
                "is_sheriff": p.is_sheriff,
                "llm_config_id": p.llm_config_id,
            }
            for pid, p in state.players.items()
        },
    }
    return response


@router.get("/{game_id}/history")
async def get_game_history(game_id: str):
    """获取游戏完整历史记录"""
    state = _active_games.get(game_id)
    if not state:
        state = GameState.load(game_id)
        if not state:
            raise HTTPException(status_code=404, detail="游戏不存在")

    settings = get_settings()
    log_path = os.path.join(settings.game_data_dir, f"game_{game_id}", "global_log.json")
    history = []
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            history = json.load(f)

    return {"game_id": game_id, "events": history}
