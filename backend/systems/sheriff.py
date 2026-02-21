"""警长竞选系统"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.state import GameState
    from ai.memory import MemoryManager

logger = logging.getLogger(__name__)


async def run_sheriff_election(
    game_state: GameState,
    get_ai_decision,  # async (player_id, phase, context) -> dict
    emit_event,       # async (event) -> None
    memory: MemoryManager | None = None,
) -> None:
    """
    执行警长竞选流程：
    1. 所有存活玩家按编号决定是否上警
    2. 上警玩家依次发表竞选演说
    3. 所有存活玩家投票（含未上警者）
    """
    alive = game_state.get_alive_ids()
    current_round = game_state.current_round

    await emit_event({"type": "game.sheriff_election", "data": {
        "phase": "start",
        "text": "警长竞选开始，请各位玩家决定是否参与竞选。",
    }})

    # --- 阶段1：决定是否上警 ---
    candidates = []
    for pid in alive:
        await emit_event({"type": "game.ai_thinking", "data": {
            "player_id": pid, "phase": "sheriff_register",
        }})
        decision = await get_ai_decision(pid, "sheriff_register", {
            "alive_players": alive,
        })
        run = decision.get("run_for_sheriff", False)
        if run:
            candidates.append(pid)
        # 实时推送每个玩家的报名决定
        await emit_event({"type": "game.sheriff_election", "data": {
            "phase": "register_decision",
            "player_id": pid,
            "run_for_sheriff": run,
        }})

    await emit_event({"type": "game.sheriff_election", "data": {
        "phase": "candidates",
        "candidates": candidates,
        "text": f"上警玩家：{'、'.join(str(p) + '号' for p in candidates)}",
    }})

    if not candidates:
        await emit_event({"type": "game.judge_narration", "data": {
            "text": "无人上警，本局无警长。",
        }})
        # 写入公开记忆：无人当选
        if memory:
            memory.add_public_event({
                "round": current_round,
                "phase": "sheriff_election",
                "event": "无人上警，本局无警长",
            })
        return

    if len(candidates) == 1:
        # 只有一人上警，直接当选
        sheriff_id = candidates[0]
        game_state.sheriff_id = sheriff_id
        game_state.sheriff_elected_round = game_state.current_round
        game_state.players[sheriff_id].is_sheriff = True
        await emit_event({"type": "game.sheriff_election", "data": {
            "phase": "elected",
            "sheriff_id": sheriff_id,
            "text": f"{sheriff_id}号玩家当选警长！",
        }})
        # 写入公开记忆：当选
        if memory:
            memory.add_public_event({
                "round": current_round,
                "phase": "sheriff_election",
                "event": f"{sheriff_id}号玩家当选警长（唯一候选人）",
            })
        return

    # --- 阶段2：竞选演说 ---
    for pid in candidates:
        await emit_event({"type": "game.ai_thinking", "data": {
            "player_id": pid, "phase": "sheriff_speech",
        }})
        decision = await get_ai_decision(pid, "sheriff_speech", {
            "candidates": candidates,
        })
        speech = decision.get("speech", f"{pid}号玩家的竞选演说...")
        await emit_event({"type": "game.speech", "data": {
            "player_id": pid,
            "content": speech,
            "is_sheriff_speech": True,
        }})
        # 广播竞选演说到所有存活玩家的记忆（Task 22）
        if memory:
            memory.broadcast_speech(pid, speech, current_round)

    # --- 阶段3：投票 ---
    votes: dict[int, int] = {}
    for voter_id in alive:
        await emit_event({"type": "game.ai_thinking", "data": {
            "player_id": voter_id, "phase": "sheriff_vote",
        }})
        decision = await get_ai_decision(voter_id, "sheriff_vote", {
            "candidates": candidates,
        })
        target = decision.get("vote_target")
        if target in candidates:
            votes[voter_id] = target
        # 实时推送每个玩家的投票
        await emit_event({"type": "game.sheriff_election", "data": {
            "phase": "vote_cast",
            "voter_id": voter_id,
            "target": votes.get(voter_id),
        }})

    # 统计票数（警长竞选时所有人1票）
    vote_counts: dict[int, int] = {}
    for target in votes.values():
        vote_counts[target] = vote_counts.get(target, 0) + 1

    await emit_event({"type": "game.sheriff_election", "data": {
        "phase": "vote_result",
        "votes": votes,
        "counts": vote_counts,
    }})

    if not vote_counts:
        await emit_event({"type": "game.judge_narration", "data": {
            "text": "无人投票，本局无警长。",
        }})
        if memory:
            memory.add_public_event({
                "round": current_round,
                "phase": "sheriff_election",
                "event": "无人投票，本局无警长",
            })
        return

    # 找最高票
    max_votes = max(vote_counts.values())
    top = [pid for pid, cnt in vote_counts.items() if cnt == max_votes]

    if len(top) > 1:
        # 平票无人当选
        await emit_event({"type": "game.judge_narration", "data": {
            "text": f"{'、'.join(str(p) + '号' for p in top)}平票，本局无警长。",
        }})
        if memory:
            memory.add_public_event({
                "round": current_round,
                "phase": "sheriff_election",
                "event": f"{'、'.join(str(p) + '号' for p in top)}平票，本局无警长",
            })
        return

    sheriff_id = top[0]
    game_state.sheriff_id = sheriff_id
    game_state.sheriff_elected_round = game_state.current_round
    game_state.players[sheriff_id].is_sheriff = True

    await emit_event({"type": "game.sheriff_election", "data": {
        "phase": "elected",
        "sheriff_id": sheriff_id,
        "text": f"{sheriff_id}号玩家当选警长！",
    }})
    # 写入公开记忆：当选
    if memory:
        memory.add_public_event({
            "round": current_round,
            "phase": "sheriff_election",
            "event": f"{sheriff_id}号玩家当选警长（得{max_votes}票）",
        })


async def handle_sheriff_death(
    game_state: GameState,
    dead_player_id: int,
    has_last_words: bool,
    get_ai_decision,
    emit_event,
    memory: MemoryManager | None = None,
) -> None:
    """
    处理警长死亡后的警徽流传承。

    - 有遗言：AI 决定传给谁或撕掉
    - 无遗言（被毒杀）：自动撕毁
    """
    player = game_state.players[dead_player_id]
    if not player.is_sheriff:
        return

    player.is_sheriff = False
    current_round = game_state.current_round

    if not has_last_words:
        # 无遗言 → 警徽撕毁
        game_state.sheriff_id = None
        await emit_event({"type": "game.sheriff_election", "data": {
            "phase": "badge_destroyed",
            "text": f"警长{dead_player_id}号死亡且无遗言，警徽撕毁，无人继承。",
        }})
        if memory:
            memory.add_public_event({
                "round": current_round,
                "phase": "badge_destroyed",
                "event": f"警长{dead_player_id}号死亡且无遗言，警徽撕毁",
            })
        return

    # 有遗言 → AI 决定警徽流
    alive = game_state.get_alive_ids()
    decision = await get_ai_decision(dead_player_id, "sheriff_badge_transfer", {
        "alive_players": alive,
    })

    successor = decision.get("successor")
    if successor and successor in alive:
        game_state.sheriff_id = successor
        game_state.players[successor].is_sheriff = True
        await emit_event({"type": "game.sheriff_election", "data": {
            "phase": "badge_transferred",
            "from": dead_player_id,
            "to": successor,
            "text": f"警长{dead_player_id}号将警徽传给了{successor}号玩家。",
        }})
        if memory:
            memory.add_public_event({
                "round": current_round,
                "phase": "badge_transferred",
                "event": f"警长{dead_player_id}号将警徽传给了{successor}号",
            })
    else:
        # 撕掉警徽
        game_state.sheriff_id = None
        await emit_event({"type": "game.sheriff_election", "data": {
            "phase": "badge_destroyed",
            "text": f"警长{dead_player_id}号选择撕掉警徽，无人继承。",
        }})
        if memory:
            memory.add_public_event({
                "round": current_round,
                "phase": "badge_destroyed",
                "event": f"警长{dead_player_id}号选择撕掉警徽",
            })
