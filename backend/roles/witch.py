"""女巫角色"""

from __future__ import annotations
from typing import TYPE_CHECKING

from roles.base import BaseRole

if TYPE_CHECKING:
    from game.state import GameState
    from models.game_models import Player


class Witch(BaseRole):
    name = "女巫"
    faction = "好人阵营"

    async def night_action(self, player: Player, game_state: GameState) -> dict:
        # 女巫的行动由引擎收集 AI 决策后设置到 night_actions
        result = {"action": "witch_decision"}
        if game_state.night_actions.witch_save:
            result["save"] = True
        if game_state.night_actions.witch_poison_target is not None:
            result["poison_target"] = game_state.night_actions.witch_poison_target
        return result

    def can_use_antidote(self, player: Player, game_state: GameState) -> bool:
        """判断女巫是否可以使用解药"""
        if player.antidote_used:
            return False
        # 首夜可以自救
        wolf_target = game_state.night_actions.wolf_target
        if wolf_target is None:
            return False  # 空刀或被守住，无人被刀
        # 非首夜不能自救
        if game_state.current_round > 1 and wolf_target == player.player_id:
            return False
        return True

    def can_use_poison(self, player: Player) -> bool:
        """判断女巫是否可以使用毒药"""
        return not player.poison_used
