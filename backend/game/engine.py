"""游戏主引擎 — 日夜循环驱动"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Callable, Awaitable, Optional, TYPE_CHECKING

from models.game_models import (
    GamePhase, NightSubPhase, DaySubPhase,
    RoleType, DeathCause,
)
from game.state import GameState
from game.resolver import resolve_night, check_hunter_trigger
from systems.sheriff import run_sheriff_election, handle_sheriff_death
from systems.voting import calculate_vote_result
from systems.speech import can_have_last_words

if TYPE_CHECKING:
    from ai.agent import AIAgent

logger = logging.getLogger(__name__)

# 事件回调类型：接收事件字典，用于 WebSocket 推送
EventCallback = Callable[[dict], Awaitable[None]]


class GameEngine:
    """游戏主引擎"""

    def __init__(
        self,
        game_state: GameState,
        event_callback: EventCallback | None = None,
        ai_agent: Optional[AIAgent] = None,
    ):
        self.state = game_state
        self.emit = event_callback or self._noop_callback
        self.ai = ai_agent  # AI 决策代理（None 时使用占位逻辑）
        self.paused = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # 初始非暂停
        self._last_hunter_shot_target: int | None = None  # 追踪猎人最近射杀目标

    @staticmethod
    async def _noop_callback(event: dict) -> None:
        pass

    async def run(self, resume: bool = False) -> None:
        """运行游戏主循环

        Args:
            resume: True 表示从持久化状态恢复，不重置回合
        """
        if not resume:
            self.state.status = "running"
            self.state.current_phase = GamePhase.NIGHT_PHASE
            self.state.current_round = 1
            self.state.save()

            # 初始化 AI 记忆
            if self.ai:
                await self.ai.init_all_memories()

            await self.emit({"type": "game.phase_change", "data": {
                "phase": "GAME_START", "round": 0,
            }})
        else:
            logger.info(f"恢复游戏 {self.state.game_id}，回合 {self.state.current_round}")

        while self.state.status == "running":
            # 暂停检查
            await self._pause_event.wait()

            # --- 夜晚阶段 ---
            self.state.current_phase = GamePhase.NIGHT_PHASE
            self.state.reset_night_actions()
            self.state.save()

            await self.emit({"type": "game.phase_change", "data": {
                "phase": "NIGHT_PHASE",
                "round": self.state.current_round,
            }})

            await self._run_night()

            # 胜利检查
            if self.state.winner:
                break

            # --- 白天阶段 ---
            self.state.current_phase = GamePhase.DAY_PHASE
            self.state.save()

            await self.emit({"type": "game.phase_change", "data": {
                "phase": "DAY_PHASE",
                "round": self.state.current_round,
            }})

            await self._run_day()

            # 胜利检查
            if self.state.winner:
                break

            # 回合递增（完整日夜循环后）
            self.state.current_round += 1

            # 20回合平局判定（完整日夜循环结束后）
            if self.state.current_round > self.state.max_rounds:
                self.state.winner = "平局"
                break

        # 游戏结束
        self.state.status = "ended"
        self.state.current_phase = GamePhase.GAME_END
        self.state.save()

        await self.emit({"type": "game.end", "data": {
            "winner": self.state.winner,
            "round": self.state.current_round,
        }})

    # ========== 夜晚阶段 ==========

    async def _run_night(self) -> None:
        """执行夜晚阶段：守卫→狼人→女巫→预言家→结算"""

        # 批量更新所有存活玩家的 current_round
        self._update_round_memories()

        # 守卫行动
        self.state.current_sub_phase = NightSubPhase.GUARD_ACTION.value
        self.state.save()
        await self._guard_phase()

        # 狼人行动
        self.state.current_sub_phase = NightSubPhase.WOLF_ACTION.value
        self.state.save()
        await self._wolf_phase()

        # 女巫行动
        self.state.current_sub_phase = NightSubPhase.WITCH_ACTION.value
        self.state.save()
        await self._witch_phase()

        # 预言家行动
        self.state.current_sub_phase = NightSubPhase.SEER_ACTION.value
        self.state.save()
        await self._seer_phase()

        # 夜晚结算
        self.state.current_sub_phase = NightSubPhase.NIGHT_RESOLVE.value
        self.state.save()
        events = resolve_night(self.state)
        for event in events:
            await self.emit({"type": "game.night_action", "data": event})
            # 夜晚死亡事件额外 emit game.death，确保前端玩家状态同步
            if event.get("type") == "death":
                await self.emit({"type": "game.death", "data": {
                    "player_id": event["player_id"],
                    "cause": event["cause"],
                    "round": event.get("round", self.state.current_round),
                }})
            if event.get("type") == "game_end":
                self.state.winner = event["winner"]

        # 写入记忆：夜晚结算结果 + 角色私有知识
        if self.ai:
            self._write_night_memories(events)

        self.state.save()

    async def _guard_phase(self) -> None:
        """守卫行动阶段"""
        guard = self.state.get_player_by_role(RoleType.GUARD)
        if not guard or not guard.is_alive:
            return

        await self._pause_event.wait()

        await self.emit({"type": "game.ai_thinking", "data": {
            "player_id": guard.player_id, "phase": "guard",
        }})

        # AI 决策将在 M6 实现，这里用占位逻辑
        target = await self._get_ai_guard_decision(guard.player_id)
        self.state.night_actions.guard_target = target
        guard.last_guarded = target

        await self.emit({"type": "game.night_action", "data": {
            "channel": "guard",
            "player_id": guard.player_id,
            "action": "guard",
            "target": target,
            "ai_notes": self._get_player_ai_notes(guard.player_id, "night_strategy"),
        }})

    async def _wolf_phase(self) -> None:
        """狼人行动阶段（多轮商量）"""
        wolves = self.state.get_alive_wolf_ids()
        if not wolves:
            return

        await self._pause_event.wait()

        await self.emit({"type": "game.ai_thinking", "data": {
            "player_ids": wolves, "phase": "wolf",
        }})

        # AI 多轮商量将在 M6 实现，这里用占位逻辑
        target = await self._get_ai_wolf_decision(wolves)
        self.state.night_actions.wolf_target = target

        await self.emit({"type": "game.night_action", "data": {
            "channel": "wolf",
            "player_ids": wolves,
            "action": "wolf_kill",
            "target": target,
            "ai_notes": {w: self._get_player_ai_notes(w, "night_strategy") for w in wolves},
        }})

    async def _witch_phase(self) -> None:
        """女巫行动阶段"""
        witch = self.state.get_player_by_role(RoleType.WITCH)
        if not witch or not witch.is_alive:
            return

        # 计算女巫可见信息
        wolf_target = self.state.night_actions.wolf_target
        guard_target = self.state.night_actions.guard_target

        # 女巫视角的被刀者（经过守卫结算）
        witch_sees_victim = None
        if wolf_target is not None and wolf_target != guard_target:
            witch_sees_victim = wolf_target
        # 守卫守住或空刀 → 女巫收到"今晚无人被刀"

        await self.emit({"type": "game.ai_thinking", "data": {
            "player_id": witch.player_id, "phase": "witch",
        }})

        await self._pause_event.wait()

        # AI 决策将在 M6 实现
        save, poison_target = await self._get_ai_witch_decision(
            witch.player_id, witch_sees_victim
        )

        # 验证解药使用条件
        if save:
            if witch.antidote_used:
                save = False
            elif witch_sees_victim is None:
                save = False  # 无人被刀，不能用解药
            elif self.state.current_round > 1 and witch_sees_victim == witch.player_id:
                save = False  # 非首夜不能自救

        if save:
            self.state.night_actions.witch_save = True
            witch.antidote_used = True

        # 验证毒药使用条件
        if poison_target is not None:
            if witch.poison_used:
                poison_target = None
            elif poison_target not in self.state.get_alive_ids():
                poison_target = None

        if poison_target is not None:
            self.state.night_actions.witch_poison_target = poison_target
            witch.poison_used = True

        await self.emit({"type": "game.night_action", "data": {
            "channel": "witch",
            "player_id": witch.player_id,
            "victim": witch_sees_victim,
            "save": save,
            "poison_target": poison_target,
            "ai_notes": self._get_player_ai_notes(witch.player_id, "night_strategy"),
        }})

    async def _seer_phase(self) -> None:
        """预言家行动阶段"""
        seer = self.state.get_player_by_role(RoleType.SEER)
        if not seer or not seer.is_alive:
            return

        await self._pause_event.wait()

        await self.emit({"type": "game.ai_thinking", "data": {
            "player_id": seer.player_id, "phase": "seer",
        }})

        # AI 决策将在 M6 实现
        target = await self._get_ai_seer_decision(seer.player_id)
        if target is not None:
            self.state.night_actions.seer_target = target
            # 计算查验结果
            target_player = self.state.players.get(target)
            if target_player:
                from models.game_models import Faction
                result = "狼人" if target_player.faction == Faction.WOLF else "好人"
                self.state.night_actions.seer_result = result

                # 即时写入预言家私有知识（不依赖 resolver 事件链）
                if self.ai:
                    self.ai.memory.update_private_knowledge(
                        seer.player_id, "check_results", {
                            "night": self.state.current_round,
                            "target": target,
                            "result": result,
                        },
                    )

        await self.emit({"type": "game.night_action", "data": {
            "channel": "seer",
            "player_id": seer.player_id,
            "target": target,
            "result": self.state.night_actions.seer_result,
            "ai_notes": self._get_player_ai_notes(seer.player_id, "night_strategy"),
        }})

    # ========== 白天阶段 ==========

    async def _run_day(self) -> None:
        """执行白天阶段"""
        is_first_day = self.state.current_round == 1

        # 警长竞选（仅第一天）
        if is_first_day:
            self.state.current_sub_phase = DaySubPhase.SHERIFF_ELECTION.value
            self.state.save()
            await run_sheriff_election(
                self.state, self._get_ai_decision, self.emit,
                memory=self.ai.memory if self.ai else None,
            )

        # 宣布死亡
        self.state.current_sub_phase = DaySubPhase.ANNOUNCE_DEATH.value
        self.state.save()
        night_deaths = await self._announce_deaths()

        # 遗言 + 猎人开枪（所有夜晚死亡都检查遗言权和猎人触发）
        if night_deaths:
            self.state.current_sub_phase = DaySubPhase.LAST_WORDS.value
            self.state.save()
            for pid in night_deaths:
                # 遗言（内部统一判断遗言权）
                words = await self._last_words(pid)
                # 猎人开枪检查（所有夜晚，不限首夜）
                trigger = check_hunter_trigger(self.state, pid)
                if trigger:
                    await self._hunter_shoot(pid, words)
                    # 猎人射杀的目标也需要处理警长死亡
                    shot_target = self._last_hunter_shot_target
                    if shot_target is not None:
                        await self._handle_death_sheriff(shot_target)
                # 处理夜晚死者的警长死亡
                await self._handle_death_sheriff(pid)

        # 胜利检查
        winner = self.state.check_victory()
        if winner:
            self.state.winner = winner
            return

        # 确定发言顺序
        self._calculate_speech_order(night_deaths)
        # 警长调整发言顺序（警长存活时可选择调整）
        await self._sheriff_adjust_speech_order()

        # 讨论发言
        self.state.current_sub_phase = DaySubPhase.DISCUSSION.value
        self.state.save()
        wolf_exploded = await self._discussion()

        if wolf_exploded:
            # 狼人自爆后检查胜利条件
            winner = self.state.check_victory()
            if winner:
                self.state.winner = winner
            return  # 狼人自爆，直接入夜

        # 胜利检查
        winner = self.state.check_victory()
        if winner:
            self.state.winner = winner
            return

        # 投票
        self.state.current_sub_phase = DaySubPhase.VOTE.value
        self.state.save()
        exiled_id = await self._vote()

        # 放逐遗言 + 猎人开枪
        if exiled_id is not None:
            self.state.current_sub_phase = DaySubPhase.EXILE_WORDS.value
            self.state.save()
            exile_words = await self._last_words(exiled_id)
            # 处理放逐者的警长死亡
            await self._handle_death_sheriff(exiled_id)
            # 检查猎人开枪
            trigger = check_hunter_trigger(self.state, exiled_id)
            if trigger:
                await self._hunter_shoot(exiled_id, exile_words)
                shot_target = self._last_hunter_shot_target
                if shot_target is not None:
                    await self._handle_death_sheriff(shot_target)

        # 胜利检查
        winner = self.state.check_victory()
        if winner:
            self.state.winner = winner

    async def _announce_deaths(self) -> list[int]:
        """宣布昨晚死亡的玩家"""
        night_deaths = [
            d.player_id for d in self.state.dead_players
            if d.round == self.state.current_round
        ]
        if night_deaths:
            text = f"天亮了，昨晚{'、'.join(str(p) + '号' for p in night_deaths)}玩家倒了。"
            await self.emit({"type": "game.judge_narration", "data": {
                "text": text,
                "deaths": night_deaths,
            }})
            # 写入公开事件记忆
            if self.ai:
                self.ai.memory.add_public_event({
                    "round": self.state.current_round,
                    "phase": "night",
                    "event": text,
                })
        else:
            await self.emit({"type": "game.judge_narration", "data": {
                "text": "天亮了，昨晚是平安夜。",
                "deaths": [],
            }})
            if self.ai:
                self.ai.memory.add_public_event({
                    "round": self.state.current_round,
                    "phase": "night",
                    "event": "平安夜，无人死亡",
                })
        return night_deaths

    def _calculate_speech_order(self, night_deaths: list[int]) -> None:
        """计算发言顺序"""
        alive = self.state.get_alive_ids()
        if self.state.current_round == 1:
            # 第一天随机
            order = alive.copy()
            random.shuffle(order)
        else:
            # 从死者下一号开始顺时针
            if night_deaths:
                base = min(night_deaths)
            else:
                base = alive[0]
            # 找到 base 的下一个存活玩家
            all_ids = sorted(self.state.players.keys())
            start_idx = None
            for i, pid in enumerate(all_ids):
                if pid > base and pid in alive:
                    start_idx = alive.index(pid)
                    break
            if start_idx is None:
                start_idx = 0  # 回到最小编号
            order = alive[start_idx:] + alive[:start_idx]

        self.state.speech_order = order

    async def _sheriff_adjust_speech_order(self) -> None:
        """警长调整发言顺序（警长存活时由 AI 决定是否调整）"""
        if self.state.sheriff_id is None:
            return
        sheriff = self.state.players.get(self.state.sheriff_id)
        if not sheriff or not sheriff.is_alive:
            return

        await self.emit({"type": "game.ai_thinking", "data": {
            "player_id": self.state.sheriff_id,
            "phase": "sheriff_adjust_order",
        }})

        decision = await self._get_ai_decision(
            self.state.sheriff_id, "sheriff_adjust_order", {
                "current_order": self.state.speech_order,
                "alive_players": self.state.get_alive_ids(),
            },
        )

        new_order = decision.get("speech_order")
        if new_order and isinstance(new_order, list):
            alive = set(self.state.get_alive_ids())
            # 验证新顺序合法性：长度一致、无重复、包含所有存活玩家
            if (len(new_order) == len(alive)
                    and len(set(new_order)) == len(new_order)
                    and set(new_order) == alive):
                self.state.speech_order = new_order
                await self.emit({"type": "game.judge_narration", "data": {
                    "text": f"警长{self.state.sheriff_id}号调整了发言顺序。",
                }})

    async def _discussion(self) -> bool:
        """白天讨论发言，返回是否有狼人自爆"""
        for player_id in self.state.speech_order:
            player = self.state.players[player_id]
            if not player.is_alive:
                continue

            await self._pause_event.wait()

            await self.emit({"type": "game.ai_thinking", "data": {
                "player_id": player_id, "phase": "discussion",
            }})

            # AI 发言决策将在 M6 实现
            speech, is_explode, parse_level = await self._get_ai_speech(player_id)

            if is_explode and player.role == RoleType.WEREWOLF:
                # 狼人自爆
                self.state.current_sub_phase = DaySubPhase.WOLF_EXPLODE.value
                self.state.kill_player(player_id, DeathCause.WOLF_EXPLODE)
                self.state.save()

                await self.emit({"type": "game.speech", "data": {
                    "player_id": player_id,
                    "content": "我是狼人，我选择自爆！",
                    "is_explode": True,
                }})

                # 自爆遗言
                await self._last_words(player_id)
                # 处理自爆者的警长死亡
                await self._handle_death_sheriff(player_id)

                await self.emit({"type": "game.judge_narration", "data": {
                    "text": f"{player_id}号玩家自爆，立即进入黑夜。",
                }})
                # 写入自爆事件到公开记忆
                if self.ai:
                    self.ai.memory.add_public_event({
                        "round": self.state.current_round,
                        "phase": "day",
                        "event": f"{player_id}号玩家自爆（狼人），立即进入黑夜",
                    })
                return True

            await self.emit({"type": "game.speech", "data": {
                "player_id": player_id,
                "content": speech,
                "ai_notes": self._get_player_ai_notes(player_id, "day_analysis"),
                "_parse_level": parse_level,
            }})

        return False

    async def _vote(self) -> int | None:
        """投票环节，返回被放逐的玩家ID或None（平票）"""
        alive = self.state.get_alive_ids()
        votes: dict[int, int] = {}  # voter -> target

        for voter_id in alive:
            await self._pause_event.wait()

            await self.emit({"type": "game.ai_thinking", "data": {
                "player_id": voter_id, "phase": "vote",
            }})

            # AI 投票决策将在 M6 实现
            target = await self._get_ai_vote(voter_id)
            if target is not None and target in alive and target != voter_id:
                votes[voter_id] = target

            # 实时推送每个玩家的投票
            await self.emit({"type": "game.vote_cast", "data": {
                "voter_id": voter_id,
                "target": votes.get(voter_id),
            }})

        # 使用投票系统计算结果（含警长1.5票权）
        exiled_id, vote_counts = calculate_vote_result(self.state, votes)

        # 写入投票记忆
        if self.ai:
            vote_result_dict = {str(k): v for k, v in vote_counts.items()}
            for voter_id in alive:
                self.ai.memory.record_vote(
                    voter_id, self.state.current_round,
                    votes.get(voter_id), vote_result_dict,
                    all_votes=votes, exiled=exiled_id,
                )

        await self.emit({"type": "game.vote", "data": {
            "votes": votes,
            "counts": vote_counts,
        }})

        if exiled_id is None:
            if not vote_counts:
                await self.emit({"type": "game.judge_narration", "data": {
                    "text": "无人投票，今天无人出局。",
                }})
                if self.ai:
                    self.ai.memory.add_public_event({
                        "round": self.state.current_round,
                        "phase": "day",
                        "event": "无人投票，今天无人出局",
                    })
            else:
                top_players = [
                    pid for pid, cnt in vote_counts.items()
                    if cnt == max(vote_counts.values())
                ]
                tie_text = f"{'、'.join(str(p) + '号' for p in top_players)}平票，今天无人出局。"
                await self.emit({"type": "game.judge_narration", "data": {
                    "text": tie_text,
                }})
                if self.ai:
                    self.ai.memory.add_public_event({
                        "round": self.state.current_round,
                        "phase": "day",
                        "event": tie_text,
                    })
            return None

        self.state.kill_player(exiled_id, DeathCause.VOTE_EXILE)
        self.state.save()

        await self.emit({"type": "game.death", "data": {
            "player_id": exiled_id,
            "cause": "vote_exile",
            "round": self.state.current_round,
        }})
        await self.emit({"type": "game.judge_narration", "data": {
            "text": f"{exiled_id}号玩家被投票放逐。",
        }})

        # 写入放逐事件到公开记忆
        if self.ai:
            self.ai.memory.add_public_event({
                "round": self.state.current_round,
                "phase": "day",
                "event": f"{exiled_id}号被投票放逐",
            })

        return exiled_id

    async def _last_words(self, player_id: int) -> str:
        """遗言环节（统一入口，所有死亡点都通过此方法）。返回遗言内容。"""
        # 统一通过 can_have_last_words 判断遗言权
        if not can_have_last_words(self.state, player_id):
            return ""

        await self.emit({"type": "game.ai_thinking", "data": {
            "player_id": player_id, "phase": "last_words",
        }})

        # AI 遗言
        speech = await self._get_ai_last_words(player_id)
        await self.emit({"type": "game.speech", "data": {
            "player_id": player_id,
            "content": speech,
            "is_last_words": True,
        }})
        return speech

    async def _hunter_shoot(self, hunter_id: int, last_words_content: str = "") -> None:
        """猎人开枪"""
        self._last_hunter_shot_target = None
        player = self.state.players[hunter_id]
        if not player.can_shoot:
            return

        await self.emit({"type": "game.ai_thinking", "data": {
            "player_id": hunter_id, "phase": "hunter_shoot",
        }})

        # AI 决策
        target = await self._get_ai_hunter_shoot(hunter_id, last_words_content)
        if target is not None and target in self.state.get_alive_ids():
            self.state.kill_player(target, DeathCause.HUNTER_SHOT)
            self._last_hunter_shot_target = target
            self.state.save()
            await self.emit({"type": "game.death", "data": {
                "player_id": target,
                "cause": "hunter_shot",
                "shooter": hunter_id,
                "round": self.state.current_round,
            }})
            await self.emit({"type": "game.judge_narration", "data": {
                "text": f"猎人{hunter_id}号亮出身份牌，带走了{target}号玩家！",
            }})
            # 写入猎人开枪事件到公开记忆
            if self.ai:
                self.ai.memory.add_public_event({
                    "round": self.state.current_round,
                    "phase": "day",
                    "event": f"猎人{hunter_id}号开枪带走了{target}号",
                })
            # 被猎人射杀的玩家有遗言
            if can_have_last_words(self.state, target):
                shot_words = await self._last_words(target)
                # 检查被射杀者是否也是猎人（连锁开枪）
                shot_trigger = check_hunter_trigger(self.state, target)
                if shot_trigger:
                    await self._hunter_shoot(target, shot_words)
                    # 连锁射杀目标也需要处理警长死亡
                    chain_target = self._last_hunter_shot_target
                    if chain_target is not None:
                        await self._handle_death_sheriff(chain_target)

    async def _handle_death_sheriff(self, dead_player_id: int) -> None:
        """处理死亡玩家的警长徽章流转"""
        player = self.state.players.get(dead_player_id)
        if not player or not player.is_sheriff:
            return
        has_words = can_have_last_words(self.state, dead_player_id)
        await handle_sheriff_death(
            self.state, dead_player_id, has_words,
            self._get_ai_decision, self.emit,
            memory=self.ai.memory if self.ai else None,
        )

    async def _get_ai_decision(
        self, player_id: int, phase: str, context: dict
    ) -> dict:
        """统一 AI 决策适配器，供 systems 模块调用"""
        if self.ai:
            return await self.ai.sheriff_decision(player_id, phase, context)
        # 占位逻辑
        if phase == "sheriff_register":
            return {"run_for_sheriff": random.random() > 0.5}
        elif phase == "sheriff_speech":
            return {"speech": f"{player_id}号玩家的竞选演说..."}
        elif phase == "sheriff_vote":
            candidates = context.get("candidates", [])
            if candidates:
                return {"vote_target": random.choice(candidates)}
            return {}
        elif phase == "sheriff_badge_transfer":
            alive = context.get("alive_players", [])
            if alive:
                return {"successor": random.choice(alive)}
            return {"successor": None}
        elif phase == "sheriff_adjust_order":
            return {}
        return {}

    # ========== AI 决策方法（有 AI Agent 时调用 LLM，否则占位） ==========

    async def _get_ai_guard_decision(self, player_id: int) -> int | None:
        """守卫 AI 决策"""
        if self.ai:
            result = await self.ai.night_action(player_id)
            target = result.get("target")
            if target is not None:
                return int(target)
            return None
        # 占位逻辑
        alive = self.state.get_alive_ids()
        player = self.state.players[player_id]
        valid = [p for p in alive if p != player.last_guarded]
        return random.choice(valid) if valid else None

    async def _get_ai_wolf_decision(self, wolf_ids: list[int]) -> int | None:
        """狼人 AI 决策（含多轮商量）"""
        if self.ai:
            return await self.ai.wolf_discussion(event_callback=self.emit)
        # 占位逻辑
        alive = self.state.get_alive_ids()
        targets = [p for p in alive if p not in wolf_ids]
        return random.choice(targets) if targets else None

    async def _get_ai_witch_decision(
        self, player_id: int, victim: int | None
    ) -> tuple[bool, int | None]:
        """女巫 AI 决策"""
        if self.ai:
            if victim is None:
                wolf_target_info = "今晚无人被狼人杀害"
            elif victim == player_id:
                wolf_target_info = f"今晚你自己（{victim}号）被狼人杀害了！你可以选择是否对自己使用解药自救。"
            else:
                wolf_target_info = f"今晚{victim}号玩家被狼人杀害"
            result = await self.ai.night_action(player_id, extra_context={
                "wolf_target_info": wolf_target_info,
            })
            save = result.get("save", False)
            poison_target = result.get("poison_target")
            if poison_target is not None:
                poison_target = int(poison_target)
            return save, poison_target
        # 占位逻辑
        save = victim is not None and not self.state.players[player_id].antidote_used
        return save, None

    async def _get_ai_seer_decision(self, player_id: int) -> int | None:
        """预言家 AI 决策"""
        if self.ai:
            result = await self.ai.night_action(player_id)
            target = result.get("target")
            if target is not None:
                return int(target)
            return None
        # 占位逻辑
        alive = self.state.get_alive_ids()
        targets = [p for p in alive if p != player_id]
        return random.choice(targets) if targets else None

    async def _get_ai_speech(self, player_id: int) -> tuple[str, bool, int]:
        """AI 发言，返回 (内容, 是否自爆, 解析降级等级)"""
        if self.ai:
            return await self.ai.day_speech(player_id)
        return f"{player_id}号玩家发言中...", False, 1

    async def _get_ai_vote(self, voter_id: int) -> int | None:
        """AI 投票"""
        if self.ai:
            return await self.ai.vote_decision(voter_id)
        # 占位逻辑
        alive = self.state.get_alive_ids()
        targets = [p for p in alive if p != voter_id]
        return random.choice(targets) if targets else None

    async def _get_ai_last_words(self, player_id: int) -> str:
        """AI 遗言"""
        if self.ai:
            return await self.ai.last_words(player_id)
        return f"{player_id}号玩家的遗言..."

    async def _get_ai_hunter_shoot(self, hunter_id: int, last_words_content: str = "") -> int | None:
        """猎人开枪 AI 决策"""
        if self.ai:
            return await self.ai.hunter_shoot(hunter_id, last_words_content)
        # 占位逻辑
        alive = self.state.get_alive_ids()
        targets = [p for p in alive if p != hunter_id]
        return random.choice(targets) if targets else None

    # ========== 辅助方法 ==========

    def _get_player_ai_notes(self, player_id: int, key: str = "") -> str:
        """从记忆中读取玩家的 AI 思考笔记（上帝视角展示用）

        ai_notes key 格式为 "round_{N}_{phase}"，此方法查找当前轮匹配 phase 的笔记。
        """
        if not self.ai:
            return ""
        memory = self.ai.memory.load(player_id)
        if key:
            # 优先查找当前轮的 round_{N}_{key}
            round_key = f"round_{memory.current_round}_{key}"
            value = memory.ai_notes.get(round_key, "")
            if value:
                return value
            # 兜底：查找最近一轮含该 phase 的笔记
            for k in reversed(sorted(memory.ai_notes.keys())):
                if k.endswith(f"_{key}") and memory.ai_notes[k]:
                    return memory.ai_notes[k]
            # 兼容旧格式
            return memory.ai_notes.get(key, "")
        # 无 key 时返回最新的笔记
        if memory.ai_notes:
            for k in reversed(sorted(memory.ai_notes.keys())):
                if memory.ai_notes[k]:
                    return memory.ai_notes[k]
        return ""

    # ========== 记忆写入 ==========

    def _write_night_memories(self, events: list[dict]) -> None:
        """将夜晚结算事件写入各角色的私有知识"""
        for event in events:
            etype = event.get("type")
            detail = event.get("detail")

            # 预言家查验结果已在 _seer_phase 中即时写入，此处跳过

            # 女巫毒杀记录 → 写入女巫私有知识
            if etype == "night_resolve" and detail == "witch_poisoned":
                witch = self.state.get_player_by_role(RoleType.WITCH)
                if witch:
                    self.ai.memory.update_private_knowledge(
                        witch.player_id, "drug_usage", {
                            "night": self.state.current_round,
                            "action": "poison",
                            "target": event.get("target"),
                        },
                    )

            # 女巫救人记录
            if etype == "night_resolve" and detail == "witch_saved":
                witch = self.state.get_player_by_role(RoleType.WITCH)
                if witch:
                    self.ai.memory.update_private_knowledge(
                        witch.player_id, "drug_usage", {
                            "night": self.state.current_round,
                            "action": "antidote",
                        },
                    )

        # 守卫守护记录 → 写入守卫私有知识
        guard = self.state.get_player_by_role(RoleType.GUARD)
        if guard and self.state.night_actions.guard_target is not None:
            self.ai.memory.update_private_knowledge(
                guard.player_id, "guard_history", {
                    "night": self.state.current_round,
                    "target": self.state.night_actions.guard_target,
                },
            )

        # 狼人击杀记录 → 写入所有狼人私有知识
        wolf_target = self.state.night_actions.wolf_target
        if wolf_target is not None:
            for wid in self.state.get_alive_wolf_ids():
                self.ai.memory.update_private_knowledge(
                    wid, "kill_history", {
                        "night": self.state.current_round,
                        "target": wolf_target,
                    },
                )

        # 女巫刀信息 → 写入女巫私有知识
        witch = self.state.get_player_by_role(RoleType.WITCH)
        if witch:
            guard_target = self.state.night_actions.guard_target
            victim = wolf_target if (wolf_target is not None and wolf_target != guard_target) else None
            self.ai.memory.update_private_knowledge(
                witch.player_id, "knife_info", {
                    "night": self.state.current_round,
                    "victim": victim,
                },
            )

    def _update_round_memories(self) -> None:
        """回合开始时批量更新所有存活玩家的 current_round"""
        if not self.ai:
            return
        for pid in self.state.get_alive_ids():
            self.ai.memory.set_round(pid, self.state.current_round)

    # ========== 游戏控制 ==========

    def pause(self) -> None:
        """暂停游戏"""
        self.paused = True
        self._pause_event.clear()

    def resume(self) -> None:
        """继续游戏"""
        self.paused = False
        self._pause_event.set()
