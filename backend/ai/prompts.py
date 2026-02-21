"""Prompt 模板系统 — 角色扮演 + 变量注入"""

from __future__ import annotations

import os
import logging
from typing import Any

import yaml

from models.game_models import RoleType

logger = logging.getLogger(__name__)

# 角色牌缓存
_role_cards: dict[str, dict] | None = None


def load_role_cards() -> dict[str, dict]:
    """加载 roles.yaml 角色牌配置"""
    global _role_cards
    if _role_cards is not None:
        return _role_cards

    yaml_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "config", "roles.yaml",
    )
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # 排除 presets 配置
    _role_cards = {k: v for k, v in data.items() if k != "presets"}
    return _role_cards


def get_role_card(role: str) -> dict:
    """获取角色牌信息"""
    cards = load_role_cards()
    return cards.get(role, {})


# ========== 系统提示词模板 ==========

SYSTEM_PROMPT_TEMPLATE = """你正在参加一场12人标准局狼人杀游戏。

【你的身份】
你是 {player_id}号玩家，角色是「{role_name}」，属于{faction}。

【角色说明】
{role_description}

【游戏规则】
- 12人局：4神职（预言家、女巫、猎人、守卫）+ 4村民 + 4狼人
- 好人阵营胜利条件：淘汰所有狼人
- 狼人阵营胜利条件：屠边（杀光所有神职 或 杀光所有平民）
- 警长拥有1.5票权
- 夜晚被狼人刀杀的玩家：无遗言，但猎人可以开枪
- 被女巫毒杀的玩家：无遗言且不能发动技能（猎人被毒不能开枪）
- 白天被投票放逐的玩家：有遗言（最后发言），猎人可以开枪
- 警长出局时可以选择移交警徽或撕毁警徽

【输出要求】
你必须严格按照 JSON 格式输出，不要包含任何其他文字。
"""

# ========== 各阶段 Prompt 模板 ==========

NIGHT_ACTION_PROMPTS: dict[str, str] = {
    "seer": """现在是第{round}夜，轮到你行动。你是{player_id}号玩家。

【当前局势】
存活玩家：{alive_players}
{memory_summary}

【你的历史查验】
{private_knowledge}

【你上轮的思考笔记】
{ai_notes}

请选择一名存活玩家进行查验（不能查验你自己{player_id}号），并写下你的思考过程。

请严格按以下 JSON 格式输出：
{{"target": 目标编号, "ai_notes": "你的分析和策略思考"}}""",

    "witch": """现在是第{round}夜，轮到你行动。你是{player_id}号玩家。

【当前局势】
存活玩家：{alive_players}
{memory_summary}

【今晚情况】
{wolf_target_info}

【重要规则提醒】
- 如果守卫守住了被刀的人，你会收到"今晚无人被刀"的信息，不存在"同守同救"的情况
- 因此：如果你看到有人被刀，说明守卫没有守住此人，你可以放心使用解药
- 夜晚被刀杀的玩家没有遗言，只有白天被投票出局的玩家才有遗言

【药水状态】
解药：{antidote_status}
毒药：{poison_status}

【你上轮的思考笔记】
{ai_notes}

请决定是否使用解药和/或毒药，并写下你的思考过程。

请严格按以下 JSON 格式输出：
{{"save": true或false, "poison_target": 毒杀目标编号或null, "ai_notes": "你的分析和策略思考"}}""",

    "guard": """现在是第{round}夜，轮到你行动。你是{player_id}号玩家。

【当前局势】
存活玩家：{alive_players}
{memory_summary}

【守护限制】
上一晚守护了：{last_guarded}（不能连续守护同一人）

【你上轮的思考笔记】
{ai_notes}

请选择一名玩家进行守护，并写下你的思考过程。

请严格按以下 JSON 格式输出：
{{"target": 目标编号, "ai_notes": "你的分析和策略思考"}}""",

    "werewolf": """现在是第{round}夜，狼人商量时间。你是{player_id}号玩家。

【当前局势】
存活玩家：{alive_players}
你的狼人队友：{wolf_teammates}
{memory_summary}

【商量记录】
{wolf_discussion}

【你上轮的思考笔记】
{ai_notes}

【发言要求】
- 你正在和队友进行夜晚密谈，请像真人对话一样回应队友的发言
- 如果队友已经发言了，你必须先回应他们的观点（同意/反对/补充），再提出自己的看法
- 不要重复队友已经说过的分析，而是提供新的角度或补充信息
- 如果你同意队友的目标，简短表态即可，重点说明你的补充理由
- 如果你不同意，明确说出分歧点和你的替代方案
- 语气自然口语化，像队友间的私下商量，不要写成分析报告
- 逻辑支撑：提出战术或新角度时，请尽量结合白天其他玩家的发言漏洞、站边或投票行为作为你的依据

请提出你的击杀目标建议和理由。

请严格按以下 JSON 格式输出：
{{"target": 目标编号, "speech": "你对队友说的话", "ai_notes": "你的分析和策略思考"}}""",
}

# ========== 白天发言两阶段 Prompt ==========

DAY_THINK_PROMPT = """现在是第{round}天，白天讨论阶段，轮到你发言前的策略思考。

【重要提醒】你是{player_id}号玩家，角色是「{role_name}」。

【当前局势】
存活玩家：{alive_players}
已出局玩家：{dead_players}
当前警长：{sheriff}
{death_announcement}
{memory_summary}

【你的私有信息】
{private_knowledge}

【你上轮的思考笔记】
{ai_notes}

{extra_context}
{wolf_context}

【角色策略指导】
{role_specific_guidance}

请基于以上信息，制定本轮的发言策略。你需要想清楚：
1. 当前局势对你的阵营是否有利？关键威胁是什么？
2. 本轮发言你要表达什么观点？推谁？保谁？
3. 哪些信息必须绝对保密（如你的真实角色、私有信息中不宜公开的部分）？
4. 哪些信息可以选择性公开来帮助你的阵营？

⚠️ 以下玩家已出局，不要将已出局玩家作为投票目标：{dead_players}

请严格按以下 JSON 格式输出：
{{"situation_analysis": "对当前局势的简要分析", "overall_strategy": "本次发言的核心目标与策略", "talking_points": ["发言要点1", "发言要点2", "发言要点3"], "must_conceal": ["绝对不能透露的信息1", "绝对不能透露的信息2"], "can_reveal": ["可以选择性透露的信息1", "可以选择性透露的信息2"]}}"""

DAY_SPEAK_PROMPT = """现在是第{round}天，白天讨论阶段，轮到你公开发言。

【重要提醒】你是{player_id}号玩家。其他玩家提到"{player_id}号"时就是在说你！

【你的发言策略】
{strategy_summary}

【当前局势】
存活玩家：{alive_players}
已出局玩家：{dead_players}
当前警长：{sheriff}
{death_announcement}
{memory_summary}

【你的私有信息】
{private_knowledge}

{extra_context}
{wolf_context}

【发言约束 — 必须严格遵守】
1. 必须覆盖你策略中的发言要点
2. 绝对不能泄露策略中标记为"必须保密"的任何信息
3. 可以选择性使用"可以透露"的信息
4. 发言风格要自然，像真人玩家一样说话，不要像在念报告
⚠️ 以下玩家已出局，不要讨论对已出局玩家的投票目标：{dead_players}
{explode_hint}

请严格按以下 JSON 格式输出：
{{"speech": "你的公开发言内容", "explode": false}}"""

# 保留原始一次性模板作为降级回退
DAY_SPEECH_PROMPT = """现在是第{round}天，白天讨论阶段，轮到你发言。

【重要提醒】你是{player_id}号玩家。其他玩家提到"{player_id}号"时就是在说你！

【当前局势】
存活玩家：{alive_players}
已出局玩家：{dead_players}
当前警长：{sheriff}
{death_announcement}
{memory_summary}

【你的私有信息】
{private_knowledge}

【你上轮的思考笔记】
{ai_notes}

{extra_context}
{wolf_context}

请发表你的看法，分析局势，表达你的立场。
注意：你是{role_name}，请根据你的角色身份和策略来发言。
⚠️ 以下玩家已出局，不要讨论对已出局玩家的投票目标：{dead_players}
{explode_hint}

请严格按以下 JSON 格式输出：
{{"speech": "你的发言内容", "explode": false, "ai_notes": "你的内心分析（不会公开）"}}"""

VOTE_PROMPT = """现在是第{round}天，投票阶段。

【重要提醒】你是{player_id}号玩家。其他玩家提到"{player_id}号"时就是在说你！

【当前局势】
存活玩家：{alive_players}
已出局玩家：{dead_players}
当前警长：{sheriff}
{memory_summary}

【你的私有信息】
{private_knowledge}

【今天的发言记录】
{today_speeches}

【你上轮的思考笔记】
{ai_notes}

{wolf_vote_context}

⚠️ 以下玩家已出局，绝对不要投票给已出局的玩家：{dead_players}
请选择一名存活玩家进行投票放逐，并写下你的投票理由。

请严格按以下 JSON 格式输出：
{{"vote_target": 目标编号, "ai_notes": "你的投票分析和理由"}}"""

LAST_WORDS_PROMPT = """你已经出局了。现在是你的遗言时间。

【你的身份】{role_name}（{faction}）
【死亡原因】{death_cause}
【当前存活玩家】{alive_players}

【你的私有信息】
{private_knowledge}

【你的记忆】
{memory_summary}

【你的思考笔记】
{ai_notes}

请发表你的遗言，可以揭示信息帮助队友。

请严格按以下 JSON 格式输出：
{{"speech": "你的遗言内容"}}"""

HUNTER_SHOOT_PROMPT = """你是猎人，你已经出局了。你可以选择开枪带走一名玩家，也可以选择不开枪。

【当前局势】
存活玩家：{alive_players}
{memory_summary}

【你的私有信息】
{private_knowledge}

【你的思考笔记】
{ai_notes}

【你刚才的遗言】
{last_words_content}

请决定是否开枪，如果开枪请选择目标。请与你的遗言保持一致。

请严格按以下 JSON 格式输出：
{{"target": 目标编号或null, "ai_notes": "你的决策理由"}}"""

# ========== 警长相关 Prompt ==========

SHERIFF_REGISTER_PROMPT = """现在是警长竞选阶段，请决定是否参与竞选。

【当前局势】
存活玩家：{alive_players}
{memory_summary}

【你上轮的思考笔记】
{ai_notes}

警长拥有1.5票权，可以决定发言顺序。请根据你的角色和策略决定是否上警。

请严格按以下 JSON 格式输出：
{{"run_for_sheriff": true或false, "ai_notes": "你的决策理由"}}"""

SHERIFF_SPEECH_PROMPT = """你正在参与警长竞选，请发表竞选演说。

【重要提醒】你是{player_id}号玩家。

【竞选者】{candidates}
【存活玩家】{alive_players}
{memory_summary}

【你的私有信息】
{private_knowledge}

【你上轮的思考笔记】
{ai_notes}

请发表你的竞选演说，争取其他玩家的支持。

请严格按以下 JSON 格式输出：
{{"speech": "你的竞选演说内容", "ai_notes": "你的竞选策略"}}"""

SHERIFF_VOTE_PROMPT = """警长竞选投票阶段，请选择你支持的候选人。

【重要提醒】你是{player_id}号玩家。

【候选人】{candidates}
【存活玩家】{alive_players}
{memory_summary}

【你的私有信息】
{private_knowledge}

【你上轮的思考笔记】
{ai_notes}

请严格按以下 JSON 格式输出：
{{"vote_target": 候选人编号, "ai_notes": "你的投票理由"}}"""

SHERIFF_BADGE_TRANSFER_PROMPT = """你是警长，你即将出局。请决定将警徽传给谁，或者选择撕掉警徽。

【重要提醒】你是{player_id}号玩家。

【存活玩家】{alive_players}
{memory_summary}

【你的私有信息】
{private_knowledge}

【你的思考笔记】
{ai_notes}

请严格按以下 JSON 格式输出：
{{"successor": 继承者编号或null(撕掉), "ai_notes": "你的决策理由"}}"""

SHERIFF_ADJUST_ORDER_PROMPT = """你是警长，你可以调整今天的发言顺序。

【当前发言顺序】{current_order}
【存活玩家】{alive_players}
{memory_summary}

【你的思考笔记】
{ai_notes}

如果你不想调整，输出空的 speech_order。

请严格按以下 JSON 格式输出：
{{"speech_order": [调整后的顺序] 或 [], "ai_notes": "你的决策理由"}}"""


def build_system_prompt(
    player_id: int,
    role: str,
    faction: str,
) -> str:
    """构建角色系统提示词"""
    card = get_role_card(role)
    role_name = card.get("name", role)
    role_desc = card.get("description", "")

    return SYSTEM_PROMPT_TEMPLATE.format(
        player_id=player_id,
        role_name=role_name,
        faction=faction,
        role_description=role_desc,
    )


def build_phase_prompt(
    phase: str,
    role: str,
    context: dict[str, Any],
) -> str:
    """
    构建阶段 Prompt，按角色信息权限注入变量。

    Args:
        phase: 阶段名称
        role: 角色类型
        context: 上下文变量字典
    """
    if phase == "night_action":
        template = NIGHT_ACTION_PROMPTS.get(role, "")
    elif phase == "day_think":
        template = DAY_THINK_PROMPT
    elif phase == "day_speak":
        template = DAY_SPEAK_PROMPT
    elif phase == "day_speech":
        template = DAY_SPEECH_PROMPT
    elif phase == "vote":
        template = VOTE_PROMPT
    elif phase == "last_words":
        template = LAST_WORDS_PROMPT
    elif phase == "hunter_shoot":
        template = HUNTER_SHOOT_PROMPT
    elif phase == "sheriff_register":
        template = SHERIFF_REGISTER_PROMPT
    elif phase == "sheriff_speech":
        template = SHERIFF_SPEECH_PROMPT
    elif phase == "sheriff_vote":
        template = SHERIFF_VOTE_PROMPT
    elif phase == "sheriff_badge_transfer":
        template = SHERIFF_BADGE_TRANSFER_PROMPT
    elif phase == "sheriff_adjust_order":
        template = SHERIFF_ADJUST_ORDER_PROMPT
    else:
        template = ""

    if not template:
        return ""

    # 安全格式化：缺失变量用空字符串替代
    try:
        return template.format_map(SafeDict(context))
    except Exception as e:
        logger.error(f"Prompt 模板格式化失败: {e}")
        return template


class SafeDict(dict):
    """安全字典，缺失 key 返回空字符串"""
    def __missing__(self, key: str) -> str:
        return ""
