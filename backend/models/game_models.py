"""游戏相关数据模型（纯数据类，不依赖 ORM）"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Faction(str, Enum):
    GOOD = "好人阵营"
    WOLF = "狼人阵营"


class RoleType(str, Enum):
    SEER = "seer"
    WITCH = "witch"
    HUNTER = "hunter"
    GUARD = "guard"
    VILLAGER = "villager"
    WEREWOLF = "werewolf"


class GamePhase(str, Enum):
    GAME_START = "GAME_START"
    NIGHT_PHASE = "NIGHT_PHASE"
    DAY_PHASE = "DAY_PHASE"
    GAME_END = "GAME_END"


class NightSubPhase(str, Enum):
    GUARD_ACTION = "GUARD_ACTION"
    WOLF_ACTION = "WOLF_ACTION"
    WITCH_ACTION = "WITCH_ACTION"
    SEER_ACTION = "SEER_ACTION"
    NIGHT_RESOLVE = "NIGHT_RESOLVE"


class DaySubPhase(str, Enum):
    SHERIFF_ELECTION = "SHERIFF_ELECTION"
    ANNOUNCE_DEATH = "ANNOUNCE_DEATH"
    LAST_WORDS = "LAST_WORDS"
    DISCUSSION = "DISCUSSION"
    VOTE = "VOTE"
    EXILE_WORDS = "EXILE_WORDS"
    WOLF_EXPLODE = "WOLF_EXPLODE"
    HUNTER_SHOOT = "HUNTER_SHOOT"


class DeathCause(str, Enum):
    WOLF_KILL = "wolf_kill"
    POISON = "poison"
    VOTE_EXILE = "vote_exile"
    WOLF_EXPLODE = "wolf_explode"
    HUNTER_SHOT = "hunter_shot"


@dataclass
class DeadPlayer:
    player_id: int
    round: int
    cause: DeathCause


@dataclass
class Player:
    """单个玩家的数据"""
    player_id: int  # 1-12
    role: RoleType
    faction: Faction
    llm_config_id: int
    is_alive: bool = True
    is_sheriff: bool = False
    # 女巫药水状态
    antidote_used: bool = False
    poison_used: bool = False
    # 守卫上一晚守护目标（用于限制连续守护）
    last_guarded: Optional[int] = None
    # 猎人能否开枪
    can_shoot: bool = True
    # 死亡信息
    death_cause: Optional[DeathCause] = None
    death_round: Optional[int] = None


ROLE_FACTION_MAP = {
    RoleType.SEER: Faction.GOOD,
    RoleType.WITCH: Faction.GOOD,
    RoleType.HUNTER: Faction.GOOD,
    RoleType.GUARD: Faction.GOOD,
    RoleType.VILLAGER: Faction.GOOD,
    RoleType.WEREWOLF: Faction.WOLF,
}

ROLE_TYPE_MAP = {
    RoleType.SEER: "神职",
    RoleType.WITCH: "神职",
    RoleType.HUNTER: "神职",
    RoleType.GUARD: "神职",
    RoleType.VILLAGER: "平民",
    RoleType.WEREWOLF: "狼人",
}
