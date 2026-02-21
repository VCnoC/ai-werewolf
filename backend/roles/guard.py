"""守卫角色"""

from __future__ import annotations
from typing import TYPE_CHECKING

from roles.base import BaseRole

if TYPE_CHECKING:
    from game.state import GameState
    from models.game_models import Player


class Guard(BaseRole):
    name = "守卫"
    faction = "好人阵营"

    async def night_action(self, player: Player, game_state: GameState) -> dict:
        target = game_state.night_actions.guard_target
        if target is not None:
            player.last_guarded = target
        return {"action": "guard", "target": target}

    def get_valid_targets(self, player: Player, game_state: GameState) -> list[int]:
        """获取守卫可守护的目标列表（排除上一晚守护的人）"""
        alive = game_state.get_alive_ids()
        if player.last_guarded is not None:
            return [pid for pid in alive if pid != player.last_guarded]
        return alive
