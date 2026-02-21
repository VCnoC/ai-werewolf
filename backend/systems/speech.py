"""发言与遗言系统"""

from __future__ import annotations

from typing import TYPE_CHECKING

from models.game_models import DeathCause

if TYPE_CHECKING:
    from game.state import GameState


def can_have_last_words(game_state: GameState, player_id: int) -> bool:
    """
    判断玩家是否有遗言权。

    规则：
    - 首夜被狼刀死亡：有遗言
    - 其他夜晚死亡（狼刀/毒杀）：无遗言
    - 白天被投票放逐：有遗言
    - 狼人自爆：有遗言
    - 被毒杀：无遗言
    """
    player = game_state.players.get(player_id)
    if not player or not player.death_cause:
        return False

    cause = player.death_cause
    death_round = player.death_round or 0

    # 被毒杀 → 无遗言
    if cause == DeathCause.POISON:
        return False

    # 白天死亡（投票放逐、狼人自爆、猎人射杀）→ 有遗言
    if cause in (DeathCause.VOTE_EXILE, DeathCause.WOLF_EXPLODE, DeathCause.HUNTER_SHOT):
        return True

    # 夜晚被狼刀
    if cause == DeathCause.WOLF_KILL:
        # 首夜有遗言，其他夜晚无遗言
        return death_round == 1

    return False
