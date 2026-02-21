"""角色基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.state import GameState
    from models.game_models import Player


class BaseRole(ABC):
    """所有角色的基类"""

    name: str = ""
    faction: str = ""

    @abstractmethod
    async def night_action(self, player: Player, game_state: GameState) -> dict:
        """夜晚行动，返回行动结果字典"""
        ...

    def can_act_at_night(self, player: Player) -> bool:
        """该角色是否有夜晚行动"""
        return True

    def on_death(self, player: Player, game_state: GameState) -> dict | None:
        """死亡时触发的效果，返回额外事件或 None"""
        return None
