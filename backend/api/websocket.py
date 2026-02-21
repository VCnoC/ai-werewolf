"""WebSocket 推送服务 — 游戏事件实时推送"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

# 游戏连接管理：game_id -> set[WebSocket]
_connections: dict[str, set[WebSocket]] = {}

# 事件缓冲：game_id -> list[dict]，用于新客户端连接时重放历史事件
_event_buffers: dict[str, list[dict]] = {}


def init_event_buffer(game_id: str) -> None:
    """初始化游戏事件缓冲区（游戏启动时调用）"""
    _event_buffers[game_id] = []


def cleanup_event_buffer(game_id: str) -> None:
    """清理游戏事件缓冲区（游戏结束时调用）"""
    _event_buffers.pop(game_id, None)


async def broadcast(game_id: str, event: dict[str, Any]) -> None:
    """向指定游戏的所有观战者广播事件，同时缓存事件用于重放"""
    # 缓存事件（无论是否有客户端连接）
    if game_id in _event_buffers:
        _event_buffers[game_id].append(event)

    clients = _connections.get(game_id, set())
    if not clients:
        return

    payload = json.dumps(event, ensure_ascii=False)
    dead: list[WebSocket] = []

    # 遍历快照，避免并发修改 set
    for ws in list(clients):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)

    # 清理断开的连接
    for ws in dead:
        clients.discard(ws)
    # 清理空集合
    if not clients:
        _connections.pop(game_id, None)


def make_event_callback(game_id: str):
    """为游戏引擎创建事件回调函数"""
    async def callback(event: dict) -> None:
        await broadcast(game_id, event)
    return callback


@router.websocket("/api/ws/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str):
    """WebSocket 观战连接端点"""
    await websocket.accept()

    # 注册连接 + 重放历史事件
    # 策略：先取缓冲快照，再注册连接，最后重放
    # 快照和注册之间无 await，不会丢失事件（Python asyncio 单线程）
    if game_id not in _connections:
        _connections[game_id] = set()
    buffered = list(_event_buffers.get(game_id, []))  # 快照（无 await，原子操作）
    _connections[game_id].add(websocket)  # 注册后新事件通过 broadcast 实时到达

    logger.info(f"观战者连接: game={game_id}, 当前连接数={len(_connections[game_id])}")

    if buffered:
        logger.info(f"重放 {len(buffered)} 条历史事件给新客户端: game={game_id}")
        for event in buffered:
            try:
                await websocket.send_text(json.dumps(event, ensure_ascii=False))
            except Exception:
                break  # 连接已断开，停止重放

    try:
        while True:
            # 接收客户端消息（暂停/继续等控制指令）
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type")

                if msg_type == "game.pause":
                    await _handle_pause(game_id)
                elif msg_type == "game.resume":
                    await _handle_resume(game_id)

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        pass
    finally:
        clients = _connections.get(game_id, set())
        clients.discard(websocket)
        if not clients:
            _connections.pop(game_id, None)
        logger.info(f"观战者断开: game={game_id}")


async def _handle_pause(game_id: str) -> None:
    """处理暂停指令"""
    from api.game import get_engine
    engine = get_engine(game_id)
    if engine:
        engine.pause()
        await broadcast(game_id, {
            "type": "game.control",
            "data": {"action": "paused"},
        })


async def _handle_resume(game_id: str) -> None:
    """处理继续指令"""
    from api.game import get_engine
    engine = get_engine(game_id)
    if engine:
        engine.resume()
        await broadcast(game_id, {
            "type": "game.control",
            "data": {"action": "resumed"},
        })
