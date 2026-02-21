"""投票系统（含警长1.5票权）"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.state import GameState

logger = logging.getLogger(__name__)


def calculate_vote_result(
    game_state: GameState,
    votes: dict[int, int],  # voter_id -> target_id
) -> tuple[int | None, dict[int, float]]:
    """
    计算投票结果。

    Args:
        game_state: 游戏状态
        votes: 投票映射 {投票者ID: 目标ID}

    Returns:
        (被放逐者ID 或 None, 票数统计)
    """
    vote_counts: dict[int, float] = {}

    for voter_id, target_id in votes.items():
        player = game_state.players.get(voter_id)
        if not player:
            continue
        # 警长1.5票权
        weight = 1.5 if player.is_sheriff else 1.0
        vote_counts[target_id] = vote_counts.get(target_id, 0) + weight

    if not vote_counts:
        return None, vote_counts

    max_votes = max(vote_counts.values())
    top_players = [pid for pid, cnt in vote_counts.items() if cnt == max_votes]

    if len(top_players) > 1:
        # 平票无人出局（含多人平票）
        return None, vote_counts

    return top_players[0], vote_counts
