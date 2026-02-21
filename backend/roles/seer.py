"""预言家角色"""

from __future__ import annotations
from typing import TYPE_CHECKING

from roles.base import BaseRole
from models.game_models import Faction

if TYPE_CHECKING:
    from game.state import GameState
    from models.game_models import Player


class Seer(BaseRole):
    name = "预言家"
    faction = "好人阵营"

    async def night_action(self, player: Player, game_state: GameState) -> dict:
        # 实际查验逻辑由引擎调用 AI 决策后执行
        # 这里定义查验结果的计算
        target_id = game_state.night_actions.seer_target
        if target_id is None:
            return {"action": "skip"}
        target = game_state.players.get(target_id)
        if not target:
            return {"action": "skip"}
        result = "狼人" if target.faction == Faction.WOLF else "好人"
        game_state.night_actions.seer_result = result
        return {"action": "check", "target": target_id, "result": result}
