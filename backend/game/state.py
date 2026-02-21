"""游戏状态管理"""

from __future__ import annotations

import json
import os
import random
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional

from config import get_settings
from models.game_models import (
    Player, DeadPlayer, DeathCause,
    RoleType, Faction, GamePhase, NightSubPhase, DaySubPhase,
    ROLE_FACTION_MAP,
)


# 标准12人局角色配置
STANDARD_ROLES = (
    [RoleType.SEER] +
    [RoleType.WITCH] +
    [RoleType.HUNTER] +
    [RoleType.GUARD] +
    [RoleType.VILLAGER] * 4 +
    [RoleType.WEREWOLF] * 4
)


@dataclass
class NightActions:
    """夜晚行动收集"""
    guard_target: Optional[int] = None
    wolf_target: Optional[int] = None  # None 表示空刀
    witch_save: bool = False
    witch_poison_target: Optional[int] = None
    seer_target: Optional[int] = None
    seer_result: Optional[str] = None  # "好人" / "狼人"


@dataclass
class GameState:
    """游戏完整状态"""
    game_id: str = ""
    status: str = "waiting"  # waiting / running / ended
    current_round: int = 0
    current_phase: GamePhase = GamePhase.GAME_START
    current_sub_phase: Optional[str] = None

    players: dict[int, Player] = field(default_factory=dict)  # player_id -> Player
    dead_players: list[DeadPlayer] = field(default_factory=list)

    sheriff_id: Optional[int] = None
    sheriff_elected_round: Optional[int] = None

    speech_order: list[int] = field(default_factory=list)
    night_actions: NightActions = field(default_factory=NightActions)

    winner: Optional[str] = None  # "好人阵营" / "狼人阵营" / "平局"
    max_rounds: int = 20

    @classmethod
    def create(cls, game_id: str, llm_config_ids: list[int]) -> GameState:
        """创建新游戏并随机分配角色"""
        if len(llm_config_ids) != 12:
            raise ValueError("需要12个 LLM 配置")

        state = cls(game_id=game_id)

        # 随机分配角色
        roles = STANDARD_ROLES.copy()
        random.shuffle(roles)

        for i, (role, config_id) in enumerate(zip(roles, llm_config_ids), start=1):
            state.players[i] = Player(
                player_id=i,
                role=role,
                faction=ROLE_FACTION_MAP[role],
                llm_config_id=config_id,
            )

        return state

    def get_alive_ids(self) -> list[int]:
        """获取存活玩家ID列表"""
        return sorted(p.player_id for p in self.players.values() if p.is_alive)

    def get_alive_wolf_ids(self) -> list[int]:
        """获取存活狼人ID列表"""
        return sorted(
            p.player_id for p in self.players.values()
            if p.is_alive and p.role == RoleType.WEREWOLF
        )

    def get_player_by_role(self, role: RoleType) -> Optional[Player]:
        """获取指定角色的玩家（单人角色）"""
        for p in self.players.values():
            if p.role == role:
                return p
        return None

    def kill_player(self, player_id: int, cause: DeathCause) -> None:
        """标记玩家死亡"""
        player = self.players[player_id]
        player.is_alive = False
        player.death_cause = cause
        player.death_round = self.current_round
        self.dead_players.append(DeadPlayer(
            player_id=player_id,
            round=self.current_round,
            cause=cause,
        ))
        # 被毒杀的猎人不能开枪
        if cause == DeathCause.POISON and player.role == RoleType.HUNTER:
            player.can_shoot = False

    def check_victory(self) -> Optional[str]:
        """检查胜利条件，返回获胜阵营或 None（狼刀在先原则）"""
        alive = [p for p in self.players.values() if p.is_alive]
        wolves_alive = [p for p in alive if p.role == RoleType.WEREWOLF]
        gods_alive = [p for p in alive if p.faction == Faction.GOOD and p.role not in (RoleType.VILLAGER,)]
        villagers_alive = [p for p in alive if p.role == RoleType.VILLAGER]

        wolf_win = not gods_alive or not villagers_alive  # 屠边
        good_win = not wolves_alive  # 狼人全灭

        # 狼刀在先原则：同时满足双方胜利条件时，狼人优先获胜
        if wolf_win and good_win:
            return "狼人阵营"
        if wolf_win:
            return "狼人阵营"
        if good_win:
            return "好人阵营"

        # 注意：20回合平局由引擎主循环判定，不在此处检查

        return None

    def reset_night_actions(self) -> None:
        """重置夜晚行动收集"""
        self.night_actions = NightActions()

    # --- 持久化 ---

    def _get_state_path(self) -> str:
        settings = get_settings()
        game_dir = os.path.join(settings.game_data_dir, f"game_{self.game_id}")
        os.makedirs(game_dir, exist_ok=True)
        return os.path.join(game_dir, "engine_state.json")

    def save(self) -> None:
        """保存游戏状态到 JSON 文件"""
        path = self._get_state_path()
        data = {
            "game_id": self.game_id,
            "status": self.status,
            "current_round": self.current_round,
            "current_phase": self.current_phase.value,
            "current_sub_phase": self.current_sub_phase,
            "alive_players": self.get_alive_ids(),
            "dead_players": [asdict(d) for d in self.dead_players],
            "sheriff": {
                "player_id": self.sheriff_id,
                "round_elected": self.sheriff_elected_round,
            } if self.sheriff_id else None,
            "role_assignments": {
                str(pid): p.role.value for pid, p in self.players.items()
            },
            "players": {
                str(pid): {
                    "role": p.role.value,
                    "faction": p.faction.value,
                    "is_alive": p.is_alive,
                    "is_sheriff": p.is_sheriff,
                    "llm_config_id": p.llm_config_id,
                    "antidote_used": p.antidote_used,
                    "poison_used": p.poison_used,
                    "last_guarded": p.last_guarded,
                    "can_shoot": p.can_shoot,
                    "death_cause": p.death_cause.value if p.death_cause else None,
                    "death_round": p.death_round,
                }
                for pid, p in self.players.items()
            },
            "speech_order": self.speech_order,
            "winner": self.winner,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, game_id: str) -> Optional[GameState]:
        """从 JSON 文件加载游戏状态"""
        settings = get_settings()
        path = os.path.join(settings.game_data_dir, f"game_{game_id}", "engine_state.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        state = cls(game_id=game_id)
        state.status = data["status"]
        state.current_round = data["current_round"]
        state.current_phase = GamePhase(data["current_phase"])
        state.current_sub_phase = data.get("current_sub_phase")
        state.speech_order = data.get("speech_order", [])
        state.winner = data.get("winner")

        if data.get("sheriff"):
            state.sheriff_id = data["sheriff"]["player_id"]
            state.sheriff_elected_round = data["sheriff"]["round_elected"]

        # 恢复玩家
        for pid_str, pdata in data["players"].items():
            pid = int(pid_str)
            state.players[pid] = Player(
                player_id=pid,
                role=RoleType(pdata["role"]),
                faction=Faction(pdata["faction"]),
                llm_config_id=pdata["llm_config_id"],
                is_alive=pdata["is_alive"],
                is_sheriff=pdata.get("is_sheriff", False),
                antidote_used=pdata.get("antidote_used", False),
                poison_used=pdata.get("poison_used", False),
                last_guarded=pdata.get("last_guarded"),
                can_shoot=pdata.get("can_shoot", True),
                death_cause=DeathCause(pdata["death_cause"]) if pdata.get("death_cause") else None,
                death_round=pdata.get("death_round"),
            )

        # 恢复死亡列表
        for d in data.get("dead_players", []):
            state.dead_players.append(DeadPlayer(
                player_id=d["player_id"],
                round=d["round"],
                cause=DeathCause(d["cause"]),
            ))

        return state
