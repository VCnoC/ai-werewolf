"""猎人角色"""

from __future__ import annotations
from typing import TYPE_CHECKING

from roles.base import BaseRole
from models.game_models import DeathCause

if TYPE_CHECKING:
    from game.state import GameState
    from models.game_models import Player


class Hunter(BaseRole):
    name = "猎人"
    faction = "好人阵营"

    async def night_action(self, player: Player, game_state: GameState) -> dict:
        return {}  # 猎人无主动夜晚行动

    def can_act_at_night(self, player: Player) -> bool:
        return False

    def on_death(self, player: Player, game_state: GameState) -> dict | None:
        """猎人死亡时判断能否开枪"""
        # 被毒杀不能开枪
        if player.death_cause == DeathCause.POISON:
            player.can_shoot = False
            return None
        # 其他死因可以开枪（由 AI 决策是否开枪及目标）
        if player.can_shoot:
            return {"trigger": "hunter_shoot", "player_id": player.player_id}
        return None
