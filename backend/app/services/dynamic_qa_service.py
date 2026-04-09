"""
动态问答引擎 — 基于 OpenAI Chat Completions 实现多轮上下文感知问答。

设计原则：
- 无额外依赖（仅 openai SDK，已在 requirements.txt）
- 与静态模式完全兼容（OPENAI_API_KEY 为空时自动降级）
- 对话历史存储在 GuideSession.conversation_history（JSONB）
- 问题数量由 LLM 决定（6～12 题），通过 is_complete 标志控制结束
"""

from typing import Dict, Any, List, Optional
import json
import re
from openai import AsyncOpenAI
from app.config import settings

# ── LLM client ────────────────────────────────────────────────────────────────
_client: Optional[AsyncOpenAI] = None


def get_client() -> Optional[AsyncOpenAI]:
    """获取 OpenAI 客户端；API Key 为空时返回 None（降级到静态模式）"""
    global _client
    if not settings.OPENAI_API_KEY:
        return None
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )
    return _client


# ── Prompts ────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
你是一位经验丰富的短视频内容策划顾问。你的任务是通过对话式问答，深入了解创作者的视频创作意图，\
为后续的 AI 剧本生成收集充分信息。

【行为准则】
1. 每次只提一个问题，简洁自然，像朋友聊天
2. 基于创作者的上一个回答，智能决定下一个最有价值的问题
3. 必须覆盖的核心维度（可灵活安排顺序）：
   - 视频主题 / 定位
   - 目标受众
   - 内容风格 / 语气
   - 目标时长
   - 参考账号或风格（可选）
   - 其他特殊要求（可选）
4. 总轮次控制在 6～10 轮，信息充足时可提前结束
5. 回答格式必须是严格的 JSON，不允许有任何 markdown 代码块

【输出格式】
每次返回如下 JSON：
{
  "question": "你想提的问题（若已完成则为空字符串）",
  "question_type": "single_choice | multi_choice | text_input",
  "options": ["选项A", "选项B"] 或 null（text_input 时为 null）,
  "is_complete": false 或 true（信息收集完毕时为 true）
}

当 is_complete 为 true 时，question 字段为空字符串。\
"""

BRIEF_SYSTEM_PROMPT = """\
你是一位专业的短视频内容策划师。根据以下创作者访谈对话，提炼出结构化的创作简报（Brief）。

输出必须是严格的 JSON，格式如下：
{
  "topic_category": "内容品类",
  "content_direction": "一句话内容方向",
  "target_audience": "目标受众描述",
  "video_style": "视频风格",
  "video_duration": "目标时长",
  "publish_frequency": "发布频率（若未提及则留空）",
  "reference_accounts": "参考账号（若未提及则留空）",
  "special_requirements": "特殊要求（若无则留空）",
  "summary": "100字以内的综合创作方向摘要"
}\
"""


# ── Core functions ──────────────────────────────────────────────────────────────

def _parse_llm_json(content: str) -> Dict:
    """解析 LLM 返回的 JSON，容错处理 markdown fence"""
    # 去掉 ```json ... ``` 包裹
    content = content.strip()
    content = re.sub(r'^```(?:json)?\s*', '', content)
    content = re.sub(r'\s*```$', '', content)
    return json.loads(content)


async def get_next_question(
    conversation_history: List[Dict[str, str]],
    answers_count: int = 0,
) -> Dict[str, Any]:
    """
    基于对话历史，让 LLM 生成下一个问题。

    Returns:
        {
            "question": str,
            "question_type": "single_choice" | "multi_choice" | "text_input",
            "options": List[str] | None,
            "is_complete": bool,
        }
    """
    client = get_client()
    if client is None:
        raise RuntimeError("OpenAI API Key not configured, dynamic mode unavailable")

    # 构造消息列表：system + 对话历史
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(conversation_history)

    # 首次问话 or 追问引导
    if not conversation_history:
        messages.append({
            "role": "user",
            "content": "你好，我想开始制作短视频，请问我。"
        })
    else:
        # 追加一个隐式提示，告知当前进度
        messages.append({
            "role": "user",
            "content": (
                f"（系统提示：已回答 {answers_count} 个问题。"
                f"{'如果信息已足够生成创作简报，请将 is_complete 设为 true。' if answers_count >= 6 else '继续引导下一个关键维度。'}）"
            )
        })

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=messages,
        temperature=0.6,
        max_tokens=512,
    )

    content = response.choices[0].message.content
    return _parse_llm_json(content)


async def generate_brief_from_history(
    conversation_history: List[Dict[str, str]],
) -> Dict[str, Any]:
    """
    基于完整对话历史，让 LLM 提炼结构化 Brief JSON。
    """
    client = get_client()
    if client is None:
        raise RuntimeError("OpenAI API Key not configured")

    # 把对话历史拼接为可读文本
    transcript_lines = []
    for msg in conversation_history:
        role_label = "顾问" if msg["role"] == "assistant" else "创作者"
        transcript_lines.append(f"{role_label}：{msg['content']}")
    transcript = "\n".join(transcript_lines)

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": BRIEF_SYSTEM_PROMPT},
            {"role": "user", "content": f"以下是访谈对话记录：\n\n{transcript}"},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    return _parse_llm_json(content)


def is_dynamic_mode_available() -> bool:
    """检查动态模式是否可用（API Key 已配置）"""
    return bool(settings.OPENAI_API_KEY)
