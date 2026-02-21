"""游戏阶段状态机"""

from __future__ import annotations

from models.game_models import GamePhase, NightSubPhase, DaySubPhase


# 夜晚子阶段顺序
NIGHT_PHASE_ORDER = [
    NightSubPhase.GUARD_ACTION,
    NightSubPhase.WOLF_ACTION,
    NightSubPhase.WITCH_ACTION,
    NightSubPhase.SEER_ACTION,
    NightSubPhase.NIGHT_RESOLVE,
]

# 白天子阶段顺序（第一天含警长竞选）
DAY_PHASE_ORDER_FIRST = [
    DaySubPhase.SHERIFF_ELECTION,
    DaySubPhase.ANNOUNCE_DEATH,
    DaySubPhase.LAST_WORDS,
    DaySubPhase.DISCUSSION,
    DaySubPhase.VOTE,
    DaySubPhase.EXILE_WORDS,
]

# 白天子阶段顺序（后续天）
DAY_PHASE_ORDER = [
    DaySubPhase.ANNOUNCE_DEATH,
    DaySubPhase.LAST_WORDS,
    DaySubPhase.DISCUSSION,
    DaySubPhase.VOTE,
    DaySubPhase.EXILE_WORDS,
]


def get_next_night_sub_phase(current: NightSubPhase | None) -> NightSubPhase | None:
    """获取下一个夜晚子阶段"""
    if current is None:
        return NIGHT_PHASE_ORDER[0]
    idx = NIGHT_PHASE_ORDER.index(current)
    if idx + 1 < len(NIGHT_PHASE_ORDER):
        return NIGHT_PHASE_ORDER[idx + 1]
    return None  # 夜晚结束


def get_next_day_sub_phase(
    current: DaySubPhase | None, is_first_day: bool
) -> DaySubPhase | None:
    """获取下一个白天子阶段"""
    order = DAY_PHASE_ORDER_FIRST if is_first_day else DAY_PHASE_ORDER
    if current is None:
        return order[0]
    if current not in order:
        return None
    idx = order.index(current)
    if idx + 1 < len(order):
        return order[idx + 1]
    return None  # 白天结束
