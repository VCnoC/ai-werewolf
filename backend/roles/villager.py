"""村民角色"""

from __future__ import annotations
from typing import TYPE_CHECKING

from roles.base import BaseRole

if TYPE_CHECKING:
    from game.state import GameState
    from models.game_models import Player


class Villager(BaseRole):
    name = "村民"
    faction = "好人阵营"

    async def night_action(self, player: Player, game_state: GameState) -> dict:
        return {}  # 村民无夜晚行动

    def can_act_at_night(self, player: Player) -> bool:
        return False
