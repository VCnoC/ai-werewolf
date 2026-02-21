"""LLM 调用客户端 — OpenAI 兼容接口封装"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# 默认超时（秒）
DEFAULT_TIMEOUT = 60
# 最大重试次数（降级第2层）
MAX_RETRIES = 2


class LLMClient:
    """OpenAI 兼容接口的 LLM 调用客户端"""

    def __init__(self, api_url: str, api_key: str, model_name: str, append_chat_path: bool = True):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.append_chat_path = append_chat_path

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """
        调用 LLM Chat Completion 接口。

        Args:
            messages: OpenAI 格式的消息列表
            temperature: 采样温度
            max_tokens: 最大输出 token 数

        Returns:
            LLM 返回的文本内容

        Raises:
            LLMCallError: 调用失败
        """
        url = f"{self.api_url}/chat/completions" if self.append_chat_path else self.api_url
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return content.strip()
            except httpx.HTTPStatusError as e:
                body = e.response.text[:300] if e.response else "无响应体"
                # temperature 不兼容时自动去掉重试
                if e.response.status_code == 400 and "temperature" in body.lower():
                    logger.warning(f"LLM 不支持 temperature={temperature}，去掉后重试: {body}")
                    payload.pop("temperature", None)
                    try:
                        resp2 = await client.post(url, json=payload, headers=headers)
                        resp2.raise_for_status()
                        data2 = resp2.json()
                        return data2["choices"][0]["message"]["content"].strip()
                    except Exception as e2:
                        raise LLMCallError(f"LLM 去掉 temperature 重试仍失败: {e2}")
                logger.error(f"LLM HTTP {e.response.status_code}: {body}")
                raise LLMCallError(f"LLM 返回错误状态码 {e.response.status_code}: {body}")
            except httpx.TimeoutException:
                raise LLMCallError("LLM 调用超时")
            except (KeyError, IndexError):
                raise LLMCallError("LLM 返回格式异常")
            except Exception as e:
                raise LLMCallError(f"LLM 调用失败: {e}")


class LLMCallError(Exception):
    """LLM 调用异常"""
    pass


# ========== 四层降级解析策略 ==========

def parse_llm_output(
    raw_text: str,
    required_fields: list[str],
    valid_targets: list[int] | None = None,
) -> dict[str, Any]:
    """
    四层降级解析 LLM 输出。

    第1层：JSON 严格解析
    第2层：（由调用方在外部重试）
    第3层：正则提取
    第4层：规则引擎兜底

    Args:
        raw_text: LLM 原始输出
        required_fields: 必须包含的字段列表
        valid_targets: 合法目标列表（用于兜底随机选择）

    Returns:
        解析后的字典，包含 _parse_level 标记解析层级
    """
    # 第1层：JSON 严格解析
    result = _try_json_parse(raw_text, required_fields)
    if result is not None:
        result["_parse_level"] = 1
        return result

    # 第3层：正则提取
    result = _try_regex_extract(raw_text, required_fields, valid_targets)
    if result is not None:
        result["_parse_level"] = 3
        logger.warning(f"LLM 输出降级到正则提取: {raw_text[:100]}")
        return result

    # 第4层：规则引擎兜底
    logger.error(f"LLM 输出降级到兜底策略: {raw_text[:100]}")
    return _fallback_result(required_fields, valid_targets)


def _try_json_parse(raw_text: str, required_fields: list[str]) -> dict | None:
    """第1层：尝试 JSON 解析"""
    # 尝试从文本中提取 JSON 块
    text = raw_text.strip()

    # 处理 markdown 代码块包裹
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        text = json_match.group(1).strip()

    # 尝试找到 JSON 对象
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        text = brace_match.group(0)

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            # 检查必须字段
            if all(f in data for f in required_fields):
                return data
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _try_regex_extract(
    raw_text: str,
    required_fields: list[str],
    valid_targets: list[int] | None,
) -> dict | None:
    """第3层：正则提取关键信息"""
    result: dict[str, Any] = {}

    for field_name in required_fields:
        if field_name == "target":
            # 提取数字目标
            numbers = re.findall(r"(\d+)\s*号", raw_text)
            if not numbers:
                numbers = re.findall(r"\b(\d{1,2})\b", raw_text)
            if numbers:
                target = int(numbers[0])
                if valid_targets and target in valid_targets:
                    result["target"] = target
                elif valid_targets:
                    continue
                else:
                    result["target"] = target

        elif field_name == "speech":
            # 安全处理：不能直接用原文（可能包含 ai_notes 等敏感信息）
            # 尝试提取引号内的发言内容
            quoted = re.findall(r'["\u201c]([^"\u201d]{5,})["\u201d]', raw_text)
            if quoted:
                result["speech"] = quoted[0].strip()
            else:
                # 无法安全提取，使用占位发言
                result["speech"] = "......"

        elif field_name == "vote_target":
            numbers = re.findall(r"(?:投|选|vote)\s*(\d+)", raw_text, re.IGNORECASE)
            if not numbers:
                numbers = re.findall(r"(\d+)\s*号", raw_text)
            if numbers:
                target = int(numbers[0])
                if valid_targets is None or target in valid_targets:
                    result["vote_target"] = target

        elif field_name == "save":
            result["save"] = bool(re.search(r"救|解药|save|antidote", raw_text, re.IGNORECASE))

        elif field_name == "poison_target":
            if re.search(r"毒|poison", raw_text, re.IGNORECASE):
                numbers = re.findall(r"(\d+)\s*号", raw_text)
                if numbers:
                    result["poison_target"] = int(numbers[-1])

        elif field_name == "run_for_sheriff":
            result["run_for_sheriff"] = bool(
                re.search(r"上警|参选|竞选|run|yes", raw_text, re.IGNORECASE)
            )

        elif field_name == "successor":
            numbers = re.findall(r"(?:传|给|指定)\s*(\d+)", raw_text)
            if not numbers:
                numbers = re.findall(r"(\d+)\s*号", raw_text)
            if numbers:
                result["successor"] = int(numbers[0])

        elif field_name == "ai_notes":
            result["ai_notes"] = raw_text.strip()

        elif field_name == "explode":
            result["explode"] = bool(re.search(r"自爆|explode", raw_text, re.IGNORECASE))

    if all(f in result for f in required_fields):
        return result
    return None


def _fallback_result(
    required_fields: list[str],
    valid_targets: list[int] | None,
) -> dict[str, Any]:
    """第4层：规则引擎兜底"""
    import random

    result: dict[str, Any] = {"_parse_level": 4, "_fallback": True}

    for field_name in required_fields:
        if field_name in ("target", "vote_target", "successor"):
            if valid_targets:
                result[field_name] = random.choice(valid_targets)
            else:
                result[field_name] = None
        elif field_name == "speech":
            result["speech"] = "......"
        elif field_name == "save":
            result["save"] = False
        elif field_name == "poison_target":
            result["poison_target"] = None
        elif field_name == "run_for_sheriff":
            result["run_for_sheriff"] = False
        elif field_name == "explode":
            result["explode"] = False
        elif field_name == "ai_notes":
            result["ai_notes"] = ""
        elif field_name == "situation_analysis":
            result["situation_analysis"] = ""
        elif field_name == "overall_strategy":
            result["overall_strategy"] = ""
        elif field_name == "talking_points":
            result["talking_points"] = []
        elif field_name == "must_conceal":
            result["must_conceal"] = []
        elif field_name == "can_reveal":
            result["can_reveal"] = []

    return result


FORMAT_REMINDER = (
    "\n\n请严格按照 JSON 格式输出，不要包含任何其他文字。"
    "输出格式示例：{}"
)
