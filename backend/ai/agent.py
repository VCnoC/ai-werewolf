"""AI Agent — 统一决策入口，串联 LLM 调用、记忆、Prompt"""

from __future__ import annotations

import logging
import random
from typing import Any

from sqlalchemy import select

from models.llm_config import LLMConfig
from models.game_models import RoleType, Faction
from game.state import GameState
from ai.llm_client import LLMClient, LLMCallError, parse_llm_output, FORMAT_REMINDER, MAX_RETRIES
from ai.memory import MemoryManager, PlayerMemory
from ai.prompts import (
    build_system_prompt, build_phase_prompt, get_role_card, load_role_cards,
)
from utils import decrypt_key

logger = logging.getLogger(__name__)


class AIAgent:
    """AI 决策代理 — 管理单局游戏的所有 AI 决策"""

    def __init__(self, game_state: GameState):
        self.state = game_state
        self.memory = MemoryManager(
            game_state.game_id,
            alive_ids_fn=lambda: game_state.get_alive_ids(),
        )
        self._llm_cache: dict[int, LLMClient] = {}  # config_id -> client

    async def init_all_memories(self) -> None:
        """初始化所有玩家的记忆文件"""
        for pid, player in self.state.players.items():
            private = self._build_initial_private_knowledge(player)
            self.memory.init_memory(
                player_id=pid,
                role=player.role.value,
                faction=player.faction.value,
                private_knowledge=private,
            )

    def _build_initial_private_knowledge(self, player) -> dict:
        """构建角色初始私有知识"""
        if player.role == RoleType.WEREWOLF:
            teammates = [
                p.player_id for p in self.state.players.values()
                if p.role == RoleType.WEREWOLF and p.player_id != player.player_id
            ]
            return {"wolf_teammates": teammates, "kill_history": []}
        elif player.role == RoleType.SEER:
            return {"check_results": []}
        elif player.role == RoleType.WITCH:
            return {"knife_info": [], "drug_usage": []}
        elif player.role == RoleType.GUARD:
            return {"guard_history": []}
        elif player.role == RoleType.HUNTER:
            return {}
        return {}

    async def _get_llm_client(self, config_id: int) -> LLMClient:
        """获取或创建 LLM 客户端（带缓存，每次查询用短生命周期 session）"""
        if config_id in self._llm_cache:
            return self._llm_cache[config_id]

        from database import async_session
        async with async_session() as db:
            result = await db.execute(
                select(LLMConfig).where(LLMConfig.id == config_id)
            )
            config = result.scalar_one_or_none()
            if not config:
                raise LLMCallError(f"LLM 配置 {config_id} 不存在")
            # 在 session 关闭前提取所有需要的字段
            client = LLMClient(
                api_url=config.api_url,
                api_key=decrypt_key(config.api_key),
                model_name=config.model_name,
                append_chat_path=config.append_chat_path if config.append_chat_path is not None else True,
            )
        self._llm_cache[config_id] = client
        return client

    async def _call_llm(
        self,
        player_id: int,
        system_prompt: str,
        user_prompt: str,
        required_fields: list[str],
        valid_targets: list[int] | None = None,
    ) -> dict[str, Any]:
        """
        调用 LLM 并解析输出（含四层降级）。

        Args:
            player_id: 玩家ID
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            required_fields: 必须字段
            valid_targets: 合法目标列表

        Returns:
            解析后的决策字典
        """
        player = self.state.players[player_id]
        try:
            client = await self._get_llm_client(player.llm_config_id)
        except LLMCallError as e:
            logger.error(f"玩家{player_id} LLM 客户端获取失败: {e}")
            from ai.llm_client import _fallback_result
            return _fallback_result(required_fields, valid_targets)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # 第1层尝试
        try:
            raw = await client.chat(messages)
            result = parse_llm_output(raw, required_fields, valid_targets)
            if result.get("_parse_level", 0) <= 1:
                return result
        except LLMCallError as e:
            logger.warning(f"玩家{player_id} LLM 第1次调用失败: {e}")
            raw = ""

        # 第2层：重试（附加格式提示）
        example = {f: "..." for f in required_fields}
        retry_msg = user_prompt + FORMAT_REMINDER.format(example)
        messages_retry = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": retry_msg},
        ]

        for attempt in range(MAX_RETRIES):
            try:
                raw = await client.chat(messages_retry)
                result = parse_llm_output(raw, required_fields, valid_targets)
                if result.get("_parse_level", 0) <= 1:
                    result["_parse_level"] = 2  # 标记为重试成功
                    return result
            except LLMCallError as e:
                logger.warning(f"玩家{player_id} LLM 重试{attempt+1}失败: {e}")

        # 第3/4层已在 parse_llm_output 中处理
        return parse_llm_output(raw or "", required_fields, valid_targets)

    def _build_context(
        self, player_id: int, phase: str, extra: dict | None = None,
    ) -> dict[str, Any]:
        """构建 Prompt 上下文变量"""
        player = self.state.players[player_id]
        memory = self.memory.load(player_id)
        card = get_role_card(player.role.value)

        # 构建已出局玩家信息
        dead_info = []
        for dp in self.state.dead_players:
            cause_map = {
                "wolf_kill": "被狼人杀害",
                "vote_exile": "被投票放逐",
                "poison": "被女巫毒杀",
                "hunter_shot": "被猎人射杀",
                "wolf_explode": "狼人自爆",
            }
            cause_str = cause_map.get(dp.cause.value if hasattr(dp.cause, 'value') else str(dp.cause), str(dp.cause))
            dead_info.append(f"{dp.player_id}号({cause_str},第{dp.round}轮)")
        dead_players_str = "、".join(dead_info) if dead_info else "暂无"

        # 警长信息
        sheriff_str = f"{self.state.sheriff_id}号" if self.state.sheriff_id else "无"

        ctx: dict[str, Any] = {
            "round": self.state.current_round,
            "player_id": player_id,
            "role_name": card.get("name", player.role.value),
            "faction": player.faction.value,
            "alive_players": str(self.state.get_alive_ids()),
            "dead_players": dead_players_str,
            "sheriff": sheriff_str,
            "memory_summary": memory.to_summary(),
            "ai_notes": _format_ai_notes(memory.ai_notes, memory.current_round),
        }

        # 角色专属上下文
        if player.role == RoleType.WEREWOLF:
            alive_wolves = self.state.get_alive_wolf_ids()
            ctx["wolf_teammates"] = str(alive_wolves)
            # 已出局的狼人队友
            all_wolf_ids = [
                p.player_id for p in self.state.players.values()
                if p.role == RoleType.WEREWOLF
            ]
            dead_wolves = [w for w in all_wolf_ids if w not in alive_wolves and w != player_id]
            ctx["dead_wolves"] = str(dead_wolves) if dead_wolves else "无"
            # 狼人白天发言上下文
            ctx["wolf_context"] = (
                f"【你的狼人队友】\n"
                f"存活队友：{ctx['wolf_teammates']}\n"
                f"已出局队友：{ctx['dead_wolves']}\n"
                f"⚠️ 发言时注意不要暴露队友身份，也不要攻击自己的队友！"
            )
            # 狼人投票上下文
            ctx["wolf_vote_context"] = (
                f"【你的狼人队友】\n"
                f"你的存活队友：{ctx['wolf_teammates']}\n"
                f"⚠️ 绝对不要投票给自己的队友！\n"
                f"作为狼人，你必须与队友统一投票目标，集中票数投给同一个好人。\n"
                f"当前存活人数较少时，狼人阵营更需要精准配合，确保每一票都投给好人阵营。"
            )
        else:
            ctx["wolf_context"] = ""
            ctx["wolf_vote_context"] = ""

        if player.role == RoleType.WITCH:
            ctx["antidote_available"] = not player.antidote_used
            ctx["poison_available"] = not player.poison_used
            ctx["antidote_status"] = "可用" if not player.antidote_used else "已使用"
            ctx["poison_status"] = "可用" if not player.poison_used else "已使用"
        elif player.role == RoleType.GUARD:
            last = player.last_guarded
            if last is None:
                ctx["last_guarded"] = "无"
            elif last == player_id:
                ctx["last_guarded"] = f"{last}号（你自己）"
            else:
                ctx["last_guarded"] = f"{last}号"

        # 私有知识
        pk = memory.private_knowledge
        if player.role == RoleType.SEER and "check_results" in pk:
            ctx["private_knowledge"] = "\n".join(
                f"第{r['night']}夜查验{r['target']}号: {r['result']}"
                for r in pk["check_results"]
            ) or "暂无查验记录"
        elif player.role == RoleType.GUARD and "guard_history" in pk:
            guard_lines = []
            for r in pk["guard_history"]:
                target = r["target"]
                label = "自己" if target == player_id else f"{target}号"
                guard_lines.append(f"第{r['night']}夜守护了{label}")
            ctx["private_knowledge"] = "\n".join(guard_lines) or "暂无守护记录"
        elif player.role == RoleType.WITCH:
            parts = []
            if "knife_info" in pk:
                for r in pk["knife_info"]:
                    victim = r.get("victim")
                    if victim is None:
                        parts.append(f"第{r['night']}夜无人被刀")
                    elif victim == player_id:
                        parts.append(f"第{r['night']}夜你自己（{victim}号）被刀")
                    else:
                        parts.append(f"第{r['night']}夜{victim}号被刀")
            if "drug_usage" in pk:
                for r in pk["drug_usage"]:
                    action = "救人" if r.get("action") == "antidote" else f"毒杀{r.get('target', '?')}号"
                    parts.append(f"第{r['night']}夜{action}")
            ctx["private_knowledge"] = "\n".join(parts) if parts else ""
        elif player.role == RoleType.WEREWOLF and "kill_history" in pk:
            ctx["private_knowledge"] = "\n".join(
                f"第{r['night']}夜刀了{r['target']}号"
                for r in pk["kill_history"]
            ) or ""
        else:
            ctx["private_knowledge"] = ""

        if extra:
            ctx.update(extra)

        return ctx

    # ========== 夜晚决策 (T6.6) ==========

    async def night_action(
        self, player_id: int, extra_context: dict | None = None,
    ) -> dict[str, Any]:
        """夜晚技能决策"""
        player = self.state.players[player_id]
        role = player.role.value
        self.memory.set_round(player_id, self.state.current_round)

        ctx = self._build_context(player_id, "night_action", extra_context)
        system = build_system_prompt(player_id, role, player.faction.value)
        user = build_phase_prompt("night_action", role, ctx)

        if not user:
            return {}

        # 确定必须字段和合法目标
        alive = self.state.get_alive_ids()
        if role == "seer":
            fields = ["target", "ai_notes"]
            targets = [p for p in alive if p != player_id]
        elif role == "witch":
            fields = ["save", "poison_target", "ai_notes"]
            targets = alive
        elif role == "guard":
            fields = ["target", "ai_notes"]
            targets = [p for p in alive if p != player.last_guarded]
        elif role == "werewolf":
            fields = ["target", "speech", "ai_notes"]
            wolves = self.state.get_alive_wolf_ids()
            targets = [p for p in alive if p not in wolves]
        else:
            return {}

        result = await self._call_llm(player_id, system, user, fields, targets)

        # 保存 AI 思考和输出到记忆
        ai_notes = {"night_strategy": result.get("ai_notes", "")}
        ai_output = {"night_action": {k: v for k, v in result.items()
                                       if not k.startswith("_") and k != "ai_notes"}}
        self.memory.update_ai_output(player_id, ai_notes=ai_notes, ai_output=ai_output)

        return result

    # ========== 白天发言 (T6.7) ==========

    # 角色专属策略引导
    _ROLE_GUIDANCE: dict[str, str] = {
        "hunter": "你是猎人，技能在被投票出局或被狼人刀杀时生效。发言中应避免暴露猎人身份，除非到了必须自证清白的生死关头。以村民或普通好人的口吻发言。",
        "werewolf": "你是狼人，目标是伪装成好人，扰乱好人阵营的判断。注意发言的逻辑一致性，避免前后矛盾被识破。不要攻击自己的狼人队友。",
        "seer": "你是预言家，拥有查验信息。需要策略性地释放查验结果，既要帮助好人阵营，又要避免过早被狼人针对。注意保护自己的安全。",
        "witch": "你是女巫，拥有用药信息。可以根据局势选择性透露你的救人/毒人信息来帮助好人阵营分析，但也要注意保护自己。",
        "guard": "你是守卫，拥有守护信息。一般不需要暴露身份，以普通好人的口吻发言即可。除非局势需要你站出来自证。",
        "villager": "你是村民，没有特殊技能信息。专注于分析其他玩家的发言和行为，找出逻辑漏洞，帮助好人阵营投票。",
    }

    def _synthesize_strategy(self, think_result: dict[str, Any]) -> str:
        """将思考阶段的结构化 JSON 压缩为策略摘要文本"""
        parts = []

        strategy = think_result.get("overall_strategy", "")
        if strategy:
            parts.append(f"核心策略：{strategy}")

        points = think_result.get("talking_points", [])
        if points:
            parts.append(f"发言要点：{'、'.join(points[:5])}")

        conceal = think_result.get("must_conceal", [])
        if conceal:
            parts.append(f"⚠️ 绝对保密：{'、'.join(conceal[:5])}")

        reveal = think_result.get("can_reveal", [])
        if reveal:
            parts.append(f"可选透露：{'、'.join(reveal[:5])}")

        return "\n".join(parts) or "（无明确策略，请根据局势自由发言）"

    async def day_speech(
        self, player_id: int, death_announcement: str = "",
    ) -> tuple[str, bool, int]:
        """
        白天发言决策（两阶段：先思考后发言）。

        Returns:
            (发言内容, 是否自爆, 解析降级等级 1-4)
        """
        player = self.state.players[player_id]
        role = player.role.value
        system = build_system_prompt(player_id, role, player.faction.value)

        extra: dict[str, Any] = {
            "death_announcement": death_announcement,
            "extra_context": "",
            "explode_hint": "",
        }
        if player.role == RoleType.WEREWOLF:
            extra["explode_hint"] = "如果你想自爆，将 explode 设为 true。"

        # ---- 第1阶段：思考 ----
        think_extra = {
            **extra,
            "role_specific_guidance": self._ROLE_GUIDANCE.get(role, "根据你的角色身份和局势来制定发言策略。"),
        }
        think_ctx = self._build_context(player_id, "day_think", think_extra)
        think_user = build_phase_prompt("day_think", role, think_ctx)

        think_result = await self._call_llm(
            player_id, system, think_user,
            ["situation_analysis", "overall_strategy", "talking_points", "must_conceal", "can_reveal"],
        )

        think_parse_level = think_result.get("_parse_level", 1)

        # 第1阶段严重失败（parse_level > 2）→ 回退到原一次性方案
        if think_parse_level > 2:
            logger.warning(f"玩家{player_id} 思考阶段降级(level={think_parse_level})，回退到一次性发言方案")
            return await self._legacy_day_speech(player_id, death_announcement)

        # ---- 第2阶段：发言 ----
        strategy_summary = self._synthesize_strategy(think_result)

        speak_extra = {
            **extra,
            "strategy_summary": strategy_summary,
        }
        speak_ctx = self._build_context(player_id, "day_speak", speak_extra)
        speak_user = build_phase_prompt("day_speak", role, speak_ctx)

        speak_result = await self._call_llm(
            player_id, system, speak_user,
            ["speech", "explode"],
        )

        speech = speak_result.get("speech", "......")
        explode = speak_result.get("explode", False)
        parse_level = speak_result.get("_parse_level", 1)

        # 保存到记忆（合并两阶段结果）
        ai_notes = {
            "day_think": {
                "situation": think_result.get("situation_analysis", ""),
                "strategy": think_result.get("overall_strategy", ""),
                "points": think_result.get("talking_points", []),
                "concealed": think_result.get("must_conceal", []),
            },
            "day_analysis": strategy_summary,
        }
        ai_output = {"day_speech": speech}
        self.memory.update_ai_output(player_id, ai_notes=ai_notes, ai_output=ai_output)

        # 广播发言到所有玩家记忆
        self.memory.broadcast_speech(
            player_id, speech, self.state.current_round,
        )

        return speech, explode, parse_level

    async def _legacy_day_speech(
        self, player_id: int, death_announcement: str = "",
    ) -> tuple[str, bool, int]:
        """原始一次性发言方案（降级回退用）"""
        player = self.state.players[player_id]
        role = player.role.value

        extra: dict[str, Any] = {
            "death_announcement": death_announcement,
            "extra_context": "",
            "explode_hint": "",
        }
        if player.role == RoleType.WEREWOLF:
            extra["explode_hint"] = "如果你想自爆，将 explode 设为 true。"

        ctx = self._build_context(player_id, "day_speech", extra)
        system = build_system_prompt(player_id, role, player.faction.value)
        user = build_phase_prompt("day_speech", role, ctx)

        result = await self._call_llm(
            player_id, system, user,
            ["speech", "explode", "ai_notes"],
        )

        speech = result.get("speech", "......")
        explode = result.get("explode", False)
        parse_level = result.get("_parse_level", 1)

        ai_notes = {"day_analysis": result.get("ai_notes", "")}
        ai_output = {"day_speech": speech}
        self.memory.update_ai_output(player_id, ai_notes=ai_notes, ai_output=ai_output)

        self.memory.broadcast_speech(
            player_id, speech, self.state.current_round,
        )

        return speech, explode, parse_level

    # ========== 投票决策 (T6.8) ==========

    async def vote_decision(self, player_id: int) -> int | None:
        """投票决策"""
        player = self.state.players[player_id]
        alive = self.state.get_alive_ids()
        targets = [p for p in alive if p != player_id]

        # 狼人投票时排除队友（fallback 安全）
        if player.role == RoleType.WEREWOLF:
            wolf_ids = self.state.get_alive_wolf_ids()
            safe_targets = [p for p in targets if p not in wolf_ids]
            if safe_targets:
                targets = safe_targets

        # 构建今天的发言记录
        memory = self.memory.load(player_id)
        speech_lines = []
        for s in memory.speeches:
            if s.get("round") == self.state.current_round:
                speaker = s["player"]
                label = "你自己" if speaker == player_id else f"{speaker}号"
                speech_lines.append(f"{label}: {s['content']}")
        today_speeches = "\n".join(speech_lines) or "暂无发言记录"

        ctx = self._build_context(player_id, "vote", {"today_speeches": today_speeches})
        system = build_system_prompt(player_id, player.role.value, player.faction.value)
        user = build_phase_prompt("vote", player.role.value, ctx)

        result = await self._call_llm(
            player_id, system, user,
            ["vote_target", "ai_notes"], targets,
        )

        vote_target = result.get("vote_target")
        if vote_target is not None:
            vote_target = int(vote_target)
            if vote_target not in targets:
                vote_target = random.choice(targets) if targets else None

        # 保存到记忆
        ai_notes = {"vote_reasoning": result.get("ai_notes", "")}
        ai_output = {"vote_target": vote_target}
        self.memory.update_ai_output(player_id, ai_notes=ai_notes, ai_output=ai_output)

        return vote_target

    # ========== 遗言 ==========

    async def last_words(self, player_id: int) -> str:
        """遗言发言"""
        player = self.state.players[player_id]
        ctx = self._build_context(player_id, "last_words", {
            "death_cause": player.death_cause.value if player.death_cause else "未知",
        })
        system = build_system_prompt(player_id, player.role.value, player.faction.value)
        user = build_phase_prompt("last_words", player.role.value, ctx)

        result = await self._call_llm(player_id, system, user, ["speech"])
        speech = result.get("speech", "......")

        # 广播遗言到所有存活玩家的记忆
        self.memory.broadcast_speech(
            player_id, f"[遗言] {speech}", self.state.current_round,
        )

        return speech

    # ========== 猎人开枪 ==========

    async def hunter_shoot(self, player_id: int, last_words_content: str = "") -> int | None:
        """猎人开枪决策"""
        alive = self.state.get_alive_ids()
        targets = [p for p in alive if p != player_id]

        ctx = self._build_context(player_id, "hunter_shoot", {
            "last_words_content": last_words_content or "（无遗言）",
        })
        system = build_system_prompt(player_id, "hunter", "好人阵营")
        user = build_phase_prompt("hunter_shoot", "hunter", ctx)

        result = await self._call_llm(
            player_id, system, user,
            ["target", "ai_notes"], targets,
        )

        target = result.get("target")
        if target is not None:
            target = int(target)
            if target not in targets:
                target = None

        return target

    # ========== 警长竞选 AI (T6.9) ==========

    async def sheriff_decision(
        self, player_id: int, phase: str, context: dict,
    ) -> dict:
        """警长相关决策（统一入口）"""
        player = self.state.players[player_id]
        ctx = self._build_context(player_id, phase, context)
        system = build_system_prompt(player_id, player.role.value, player.faction.value)
        user = build_phase_prompt(phase, player.role.value, ctx)

        if phase == "sheriff_register":
            fields = ["run_for_sheriff", "ai_notes"]
            targets = None
        elif phase == "sheriff_speech":
            fields = ["speech", "ai_notes"]
            targets = None
        elif phase == "sheriff_vote":
            fields = ["vote_target", "ai_notes"]
            targets = context.get("candidates", [])
        elif phase == "sheriff_badge_transfer":
            fields = ["successor", "ai_notes"]
            targets = context.get("alive_players", [])
        elif phase == "sheriff_adjust_order":
            fields = ["speech_order", "ai_notes"]
            targets = None
        else:
            return {}

        result = await self._call_llm(player_id, system, user, fields, targets)

        # 保存思考笔记
        if result.get("ai_notes"):
            self.memory.update_ai_output(
                player_id,
                ai_notes={"sheriff_strategy": result["ai_notes"]},
            )

        return result

    # ========== 狼人多轮商量 (T6.10) ==========

    async def wolf_discussion(self, event_callback=None) -> int | None:
        """
        狼人多轮商量机制。

        流程：
        1. 第1-3轮：每个狼人提出目标+理由
        2. 第4轮起：检查是否达成一致（≥半数）
        3. 第6轮：强制决定（多数决/编号最小狼人决定）

        Returns:
            最终击杀目标ID 或 None（空刀）
        """
        wolves = self.state.get_alive_wolf_ids()
        if not wolves:
            return None

        alive = self.state.get_alive_ids()
        non_wolf_targets = [p for p in alive if p not in wolves]
        if not non_wolf_targets:
            return None

        discussion_log: list[dict] = []
        min_rounds = 2
        max_rounds = 6

        for round_num in range(1, max_rounds + 1):
            round_proposals: dict[int, int] = {}  # wolf_id -> target

            for wolf_id in wolves:
                # 构建商量上下文，区分"你"和"队友"的发言
                disc_lines = []
                for d in discussion_log:
                    speaker = "你" if d["wolf_id"] == wolf_id else f"队友{d['wolf_id']}号"
                    disc_lines.append(
                        f"[第{d['round']}轮] {speaker}: 建议刀{d['target']}号 — \u201c{d['speech']}\u201d"
                    )
                disc_text = "\n".join(disc_lines) or "（第一轮，尚无讨论记录）"

                ctx = self._build_context(wolf_id, "night_action", {
                    "wolf_discussion": disc_text,
                })
                system = build_system_prompt(
                    wolf_id, "werewolf",
                    self.state.players[wolf_id].faction.value,
                )
                user = build_phase_prompt("night_action", "werewolf", ctx)

                result = await self._call_llm(
                    wolf_id, system, user,
                    ["target", "speech", "ai_notes"],
                    non_wolf_targets,
                )

                target = result.get("target")
                if target is not None:
                    target = int(target)
                    if target not in non_wolf_targets:
                        target = random.choice(non_wolf_targets)
                else:
                    target = random.choice(non_wolf_targets)

                round_proposals[wolf_id] = target
                discussion_log.append({
                    "round": round_num,
                    "wolf_id": wolf_id,
                    "target": target,
                    "speech": result.get("speech", "..."),
                })

                # 实时推送狼人讨论过程
                if event_callback:
                    await event_callback({"type": "game.wolf_discussion", "data": {
                        "discussion_round": round_num,
                        "wolf_id": wolf_id,
                        "target": target,
                        "speech": result.get("speech", "..."),
                        "ai_notes": result.get("ai_notes", ""),
                    }})

                # 保存狼人商量记录到记忆
                self.memory.update_ai_output(
                    wolf_id,
                    ai_notes={"night_strategy": result.get("ai_notes", "")},
                    ai_output={"night_action": {"target": target}},
                )

            # 最少讨论轮数后才检查一致性（3.16规范）
            if round_num > min_rounds:
                consensus = _check_wolf_consensus(round_proposals, wolves)
                if consensus is not None:
                    logger.info(
                        f"狼人在第{round_num}轮达成一致: 刀{consensus}号"
                    )
                    self._save_wolf_discussion_memory(discussion_log, wolves, consensus)
                    return consensus

        # 第6轮仍未一致：多数决 / 编号最小狼人决定
        final_target = _force_wolf_decision(discussion_log, wolves, non_wolf_targets)
        self._save_wolf_discussion_memory(discussion_log, wolves, final_target)
        return final_target

    def _save_wolf_discussion_memory(
        self, discussion_log: list[dict], wolves: list[int], final_target: int,
    ) -> None:
        """将狼人商量记录写入所有狼人的记忆（仅狼人可见）"""
        current_round = self.state.current_round

        # 摘要事件
        summary = f"第{current_round}夜狼人商量，最终决定刀{final_target}号"
        self.memory.add_public_event(
            {
                "round": current_round,
                "phase": "wolf_discussion",
                "event": summary,
            },
            player_ids=wolves,
        )

        # 详细讨论内容写入每个狼人的 ai_notes（按轮次前缀存储）
        detail_lines = []
        for entry in discussion_log:
            wid = entry.get("wolf_id", "?")
            target = entry.get("target", "?")
            speech = entry.get("speech", "")[:80]  # 截取前80字
            detail_lines.append(f"  {wid}号建议刀{target}号: {speech}")
        detail_lines.append(f"  → 最终决定: 刀{final_target}号")
        detail_text = "\n".join(detail_lines)

        for wolf_id in wolves:
            self.memory.update_ai_output(
                wolf_id,
                ai_notes={"wolf_discussion": detail_text},
                round_num=current_round,
            )


def _check_wolf_consensus(
    proposals: dict[int, int], wolves: list[int],
) -> int | None:
    """检查狼人是否达成一致（≥半数同意）"""
    from collections import Counter
    counts = Counter(proposals.values())
    threshold = len(wolves) / 2
    for target, count in counts.most_common():
        if count >= threshold:
            return target
    return None


def _force_wolf_decision(
    discussion_log: list[dict],
    wolves: list[int],
    valid_targets: list[int],
) -> int:
    """强制决定：最后一轮多数决，平票由编号最小狼人决定"""
    from collections import Counter

    # 取最后一轮的提议
    if not discussion_log:
        return random.choice(valid_targets)

    last_round = max(d["round"] for d in discussion_log)
    last_proposals = [
        d["target"] for d in discussion_log if d["round"] == last_round
    ]

    counts = Counter(last_proposals)
    max_count = max(counts.values())
    top_targets = [t for t, c in counts.items() if c == max_count]

    if len(top_targets) == 1:
        return top_targets[0]

    # 平票：编号最小狼人的选择
    min_wolf = min(wolves)
    for d in discussion_log:
        if d["round"] == last_round and d["wolf_id"] == min_wolf:
            return d["target"]

    return random.choice(valid_targets)


def _format_ai_notes(notes: dict[str, str], current_round: int = 0) -> str:
    """格式化 AI 笔记为可读文本（按轮次分组，展示最近2-3轮）

    ai_notes key 格式为 "round_{N}_{phase}"，如 "round_1_night_strategy"。
    兼容旧格式（无 round_ 前缀）。
    """
    if not notes:
        return "暂无历史思考笔记"

    phase_label_map = {
        "night_strategy": "夜晚策略",
        "day_analysis": "白天分析",
        "vote_reasoning": "投票理由",
        "sheriff_strategy": "警长策略",
        "wolf_discussion": "狼人商量",
    }

    # 按轮次分组
    rounds: dict[int, list[tuple[str, str]]] = {}
    legacy_notes: list[tuple[str, str]] = []

    for key, value in notes.items():
        if not value:
            continue
        if key.startswith("round_"):
            # 解析 "round_{N}_{phase}" 格式
            parts = key.split("_", 2)  # ["round", "N", "phase_name"]
            if len(parts) >= 3:
                try:
                    rn = int(parts[1])
                    phase = parts[2]
                    rounds.setdefault(rn, []).append((phase, value))
                except ValueError:
                    legacy_notes.append((key, value))
            else:
                legacy_notes.append((key, value))
        else:
            # 兼容旧格式
            legacy_notes.append((key, value))

    lines = []

    # 确定展示范围：最近 2-3 轮
    if rounds:
        sorted_rounds = sorted(rounds.keys())
        # 展示最近3轮，当前轮完整展示，历史轮摘要
        recent_rounds = sorted_rounds[-3:]
        for rn in recent_rounds:
            entries = rounds[rn]
            is_current = (rn == current_round) or (rn == sorted_rounds[-1])
            lines.append(f"--- 第{rn}轮 ---")
            for phase, value in entries:
                label = phase_label_map.get(phase, phase)
                if is_current:
                    lines.append(f"  [{label}] {value}")
                else:
                    # 历史轮次截取前80字
                    truncated = value[:80] + "..." if len(value) > 80 else value
                    lines.append(f"  [{label}] {truncated}")

    # 兼容旧格式笔记
    if legacy_notes:
        for key, value in legacy_notes:
            label = phase_label_map.get(key, key)
            lines.append(f"[{label}] {value}")

    return "\n".join(lines) if lines else "暂无历史思考笔记"
