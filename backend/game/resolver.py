"""结算引擎 — 夜晚结算、胜利判定"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from models.game_models import DeathCause, RoleType

if TYPE_CHECKING:
    from game.state import GameState

logger = logging.getLogger(__name__)


def resolve_night(game_state: GameState) -> list[dict]:
    """
    夜晚结算算法，返回事件列表。

    结算顺序：
    1. 收集守卫守护目标
    2. 收集狼人击杀目标
    3. 判断击杀是否生效（守卫守住 → 无效）
    4. 女巫决策（解药/毒药）
    5. 计算最终死亡列表
    6. 预言家查验结果
    7. 胜利条件检查
    """
    actions = game_state.night_actions
    events: list[dict] = []
    deaths: list[tuple[int, DeathCause]] = []

    guard_target = actions.guard_target
    wolf_target = actions.wolf_target

    # --- 步骤1-3：判断狼刀是否生效 ---
    wolf_kill_effective = False
    actual_wolf_victim = None

    if wolf_target is not None:
        if wolf_target == guard_target:
            # 守卫守住了
            logger.info(f"守卫守住了 {wolf_target} 号玩家")
            events.append({
                "type": "night_resolve",
                "detail": "guard_blocked",
                "guard_target": guard_target,
                "wolf_target": wolf_target,
            })
        else:
            wolf_kill_effective = True
            actual_wolf_victim = wolf_target
    else:
        # 空刀
        logger.info("狼人选择空刀")
        events.append({"type": "night_resolve", "detail": "wolf_empty_knife"})

    # --- 步骤4-5：女巫决策 + 最终死亡列表 ---

    # 女巫救人
    if actions.witch_save and actual_wolf_victim is not None:
        logger.info(f"女巫救了 {actual_wolf_victim} 号玩家")
        wolf_kill_effective = False
        actual_wolf_victim = None
        events.append({"type": "night_resolve", "detail": "witch_saved"})

    # 狼刀最终生效
    if wolf_kill_effective and actual_wolf_victim is not None:
        deaths.append((actual_wolf_victim, DeathCause.WOLF_KILL))

    # 女巫毒杀（独立于守护判定，毒药无法被守卫挡住）
    if actions.witch_poison_target is not None:
        poison_target = actions.witch_poison_target
        # 即使被守卫守护，毒药仍然生效
        deaths.append((poison_target, DeathCause.POISON))
        events.append({
            "type": "night_resolve",
            "detail": "witch_poisoned",
            "target": poison_target,
        })

    # --- 步骤5.5：同守同救处理 ---
    # 如果守卫守住 + 女巫救 → 正常存活（当前信息流下不会触发，但保留防御性逻辑）
    # 已在上方逻辑中自然处理：守卫守住 → wolf_kill_effective=False → 女巫收到"无人被刀" → 不会用解药

    # --- 执行死亡（同一目标被多种方式击杀时，毒杀优先） ---
    # 按玩家聚合死因，毒杀优先级高于狼刀
    death_map: dict[int, DeathCause] = {}
    for player_id, cause in deaths:
        if player_id in death_map:
            # 毒杀优先（压制遗言和猎人开枪）
            if cause == DeathCause.POISON:
                death_map[player_id] = cause
        else:
            death_map[player_id] = cause

    death_ids = []
    for player_id, cause in death_map.items():
        player = game_state.players.get(player_id)
        if player and player.is_alive:
            game_state.kill_player(player_id, cause)
            death_ids.append(player_id)
            events.append({
                "type": "death",
                "player_id": player_id,
                "cause": cause.value,
                "round": game_state.current_round,
            })

    # --- 步骤6：预言家查验 ---
    if actions.seer_target is not None and actions.seer_result is not None:
        events.append({
            "type": "seer_result",
            "target": actions.seer_target,
            "result": actions.seer_result,
        })

    # --- 步骤7：胜利条件检查（狼刀在先原则） ---
    winner = game_state.check_victory()
    if winner:
        events.append({"type": "game_end", "winner": winner})

    # 平安夜
    if not death_ids:
        events.append({"type": "night_resolve", "detail": "peaceful_night"})

    return events


def check_hunter_trigger(game_state: GameState, dead_player_id: int) -> dict | None:
    """检查猎人死亡是否触发开枪"""
    player = game_state.players.get(dead_player_id)
    if not player or player.role != RoleType.HUNTER:
        return None
    if player.death_cause == DeathCause.POISON:
        return None  # 被毒杀不能开枪
    if player.can_shoot:
        return {"trigger": "hunter_shoot", "player_id": dead_player_id}
    return None


def check_victory(game_state: GameState) -> str | None:
    """检查胜利条件"""
    return game_state.check_victory()
