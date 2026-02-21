"""AI 记忆文件系统 — 每个玩家独立 JSON 记忆"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class PlayerMemory:
    """单个玩家的记忆数据"""
    player_id: int = 0
    role: str = ""
    faction: str = ""
    current_round: int = 0

    # 角色私有知识（按角色不同内容不同）
    private_knowledge: dict[str, Any] = field(default_factory=dict)

    # 公开事件记录
    public_events: list[dict[str, Any]] = field(default_factory=list)

    # 所有人的发言记录
    speeches: list[dict[str, Any]] = field(default_factory=list)

    # 投票历史
    vote_history: list[dict[str, Any]] = field(default_factory=list)

    # AI 内部思考笔记（私有，不泄露给其他玩家）
    # 按轮次存储：key 格式为 "round_{N}_{phase}" 如 "round_1_night_strategy"
    ai_notes: dict[str, str] = field(default_factory=dict)

    # AI 最终输出（行为记录）
    ai_output: dict[str, Any] = field(default_factory=dict)

    def to_summary(self) -> str:
        """生成记忆摘要，用于注入 Prompt"""
        lines = []

        # 公开事件
        if self.public_events:
            lines.append("【已知事件】")
            for evt in self.public_events[-20:]:  # 最近20条
                lines.append(f"  第{evt.get('round', '?')}轮 {evt.get('phase', '')}: {evt.get('event', '')}")

        # 发言记录（最近2-3轮，当前轮完整，历史轮摘要）
        if self.speeches:
            # 按轮次分组
            speeches_by_round: dict[int, list[dict]] = {}
            for s in self.speeches:
                rn = s.get("round", 0)
                speeches_by_round.setdefault(rn, []).append(s)

            sorted_rounds = sorted(speeches_by_round.keys())
            # 展示最近3轮
            recent_rounds = sorted_rounds[-3:]

            if recent_rounds:
                lines.append("【近期发言】")
                for rn in recent_rounds:
                    round_speeches = speeches_by_round[rn]
                    is_current = (rn == self.current_round) or (rn == sorted_rounds[-1])
                    lines.append(f"  -- 第{rn}轮 --")
                    for s in round_speeches:
                        speaker = s.get('player', '?')
                        label = "你自己" if speaker == self.player_id else f"{speaker}号"
                        content = s.get('content', '')
                        if is_current:
                            # 当前轮完整展示（截取前150字）
                            lines.append(f"    {label}: {content[:150]}")
                        else:
                            # 历史轮摘要（截取前60字）
                            lines.append(f"    {label}: {content[:60]}{'...' if len(content) > 60 else ''}")

        # 投票历史
        if self.vote_history:
            lines.append("【投票记录】")
            for v in self.vote_history[-5:]:
                rn = v.get('round', '?')
                my_vote = v.get('my_vote', '?')
                exiled = v.get('exiled')
                all_votes = v.get('all_votes', {})

                vote_line = f"  第{rn}轮 我投了{my_vote}号"
                if exiled:
                    vote_line += f" → {exiled}号被放逐"
                elif exiled is None and all_votes:
                    vote_line += " → 平票无人出局"
                lines.append(vote_line)

                # 展示完整投票映射（最近2轮）
                if all_votes and v in self.vote_history[-2:]:
                    vote_details = [f"{k}号→{val}号" for k, val in all_votes.items()]
                    lines.append(f"    投票详情: {', '.join(vote_details)}")

        return "\n".join(lines) if lines else "暂无历史记忆"


class MemoryManager:
    """记忆文件管理器"""

    def __init__(self, game_id: str, alive_ids_fn=None):
        self.game_id = game_id
        self._alive_ids_fn = alive_ids_fn  # 可选：返回存活玩家ID列表的回调
        settings = get_settings()
        self.memory_dir = os.path.join(
            settings.game_data_dir, f"game_{game_id}", "memory"
        )
        os.makedirs(self.memory_dir, exist_ok=True)

    def _get_alive_ids(self) -> set[int] | None:
        """获取存活玩家ID集合，无回调时返回 None（不过滤）"""
        if self._alive_ids_fn:
            return set(self._alive_ids_fn())
        return None

    def _get_path(self, player_id: int) -> str:
        return os.path.join(self.memory_dir, f"player_{player_id:02d}.json")

    def init_memory(
        self, player_id: int, role: str, faction: str,
        private_knowledge: dict | None = None,
    ) -> PlayerMemory:
        """初始化玩家记忆文件"""
        memory = PlayerMemory(
            player_id=player_id,
            role=role,
            faction=faction,
            current_round=1,
            private_knowledge=private_knowledge or {},
        )
        self.save(memory)
        return memory

    def load(self, player_id: int) -> PlayerMemory:
        """读取玩家记忆"""
        path = self._get_path(player_id)
        if not os.path.exists(path):
            return PlayerMemory(player_id=player_id)

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return PlayerMemory(**data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"读取玩家{player_id}记忆失败: {e}")
            return PlayerMemory(player_id=player_id)

    def save(self, memory: PlayerMemory) -> None:
        """保存玩家记忆"""
        path = self._get_path(memory.player_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(memory), f, ensure_ascii=False, indent=2)

    def add_public_event(self, event: dict, player_ids: list[int] | None = None) -> None:
        """向指定玩家（或所有存活玩家）写入公开事件"""
        if player_ids is None:
            # 仅写入存活玩家（死者不再需要新事件）
            alive = self._get_alive_ids()
            player_ids = [pid for pid in self._get_all_player_ids()
                          if alive is None or pid in alive]

        for pid in player_ids:
            memory = self.load(pid)
            memory.public_events.append(event)
            self.save(memory)

    def broadcast_speech(
        self, speaker_id: int, content: str, round_num: int,
        exclude_ids: list[int] | None = None,
    ) -> None:
        """
        广播发言到所有存活玩家的记忆。

        信息隔离规则：
        - 发言内容写入所有存活玩家的 speeches[]
        - ai_notes 绝不泄露给其他玩家
        """
        speech_record = {
            "round": round_num,
            "player": speaker_id,
            "content": content,
        }
        exclude = set(exclude_ids or [])
        alive = self._get_alive_ids()
        for pid in self._get_all_player_ids():
            if pid in exclude:
                continue
            if alive is not None and pid not in alive:
                continue  # 跳过死亡玩家
            memory = self.load(pid)
            memory.speeches.append(speech_record)
            self.save(memory)

    def update_ai_output(
        self, player_id: int,
        ai_notes: dict[str, str] | None = None,
        ai_output: dict[str, Any] | None = None,
        round_num: int | None = None,
    ) -> None:
        """
        更新玩家自己的 AI 思考和输出。

        ai_notes 按轮次存储，key 格式为 "round_{N}_{phase}"，避免覆盖历史思考。
        仅写入自己的记忆文件，绝不泄露给其他玩家。
        """
        memory = self.load(player_id)
        if ai_notes:
            rn = round_num or memory.current_round
            for key, value in ai_notes.items():
                round_key = f"round_{rn}_{key}"
                memory.ai_notes[round_key] = value
        if ai_output:
            memory.ai_output.update(ai_output)
        self.save(memory)

    def update_private_knowledge(
        self, player_id: int, key: str, value: Any,
    ) -> None:
        """更新角色私有知识"""
        memory = self.load(player_id)
        if key in memory.private_knowledge and isinstance(memory.private_knowledge[key], list):
            memory.private_knowledge[key].append(value)
        else:
            memory.private_knowledge[key] = value
        self.save(memory)

    def record_vote(
        self, player_id: int, round_num: int,
        my_vote: int | None, result: dict | None = None,
        all_votes: dict[int, int] | None = None,
        exiled: int | None = None,
    ) -> None:
        """记录投票（含完整投票映射和放逐结果）"""
        memory = self.load(player_id)
        vote_record: dict[str, Any] = {
            "round": round_num,
            "my_vote": my_vote,
            "result": result,
        }
        if all_votes:
            # 完整投票映射：谁投了谁
            vote_record["all_votes"] = {str(k): v for k, v in all_votes.items()}
        if exiled is not None:
            vote_record["exiled"] = exiled
        memory.vote_history.append(vote_record)
        self.save(memory)

    def set_round(self, player_id: int, round_num: int) -> None:
        """更新当前回合"""
        memory = self.load(player_id)
        memory.current_round = round_num
        self.save(memory)

    def _get_all_player_ids(self) -> list[int]:
        """获取所有已有记忆文件的玩家ID"""
        ids = []
        if not os.path.exists(self.memory_dir):
            return ids
        for fname in os.listdir(self.memory_dir):
            if fname.startswith("player_") and fname.endswith(".json"):
                try:
                    pid = int(fname.replace("player_", "").replace(".json", ""))
                    ids.append(pid)
                except ValueError:
                    pass
        return sorted(ids)
