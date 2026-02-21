"""狼人角色"""

from __future__ import annotations
from typing import TYPE_CHECKING

from roles.base import BaseRole

if TYPE_CHECKING:
    from game.state import GameState
    from models.game_models import Player


class Werewolf(BaseRole):
    name = "狼人"
    faction = "狼人阵营"

    async def night_action(self, player: Player, game_state: GameState) -> dict:
        # 狼人的击杀目标由多轮商量后确定，存储在 night_actions.wolf_target
        return {"action": "wolf_kill", "target": game_state.night_actions.wolf_target}

    def get_teammates(self, player: Player, game_state: GameState) -> list[int]:
        """获取狼人队友ID列表"""
        return [
            p.player_id for p in game_state.players.values()
            if p.role.value == "werewolf" and p.player_id != player.player_id
        ]
