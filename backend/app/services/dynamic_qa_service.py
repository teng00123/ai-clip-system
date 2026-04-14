"""
动态问答引擎 — 基于 LangChain + ChatOpenAI 实现多轮上下文感知问答。

设计原则：
- 使用 LangChain 统一调用，兼容 gpt-3.5-turbo 等不支持 response_format 的模型
- 与静态模式完全兼容（OPENAI_API_KEY 为空时自动降级）
- 对话历史存储在 GuideSession.conversation_history（JSONB）
- 问题数量由 LLM 决定（6～10 题），通过 is_complete 标志控制结束
"""

from typing import Dict, Any, List, Optional
import json
import re

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser

from app.config import settings


# ── LLM 工厂 ──────────────────────────────────────────────────────────────────

def _make_llm() -> Optional[ChatOpenAI]:
    """API Key 为空时返回 None（降级到静态模式）"""
    if not settings.OPENAI_API_KEY:
        return None
    return ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        temperature=0.6,
    )


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

当 is_complete 为 true 时，question 字段为空字符串。"""

BRIEF_SYSTEM_PROMPT = """\
你是一位专业的短视频内容策划师。根据以下创作者访谈对话，提炼出结构化的创作简报（Brief）。

输出必须是严格的 JSON，不要加 markdown 代码块，格式如下：
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
}"""


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _parse_llm_json(content: str) -> Dict:
    """解析 LLM 返回的 JSON，容错处理 markdown fence 和前后说明文字"""
    content = content.strip()
    content = re.sub(r'^```(?:json)?\s*', '', content)
    content = re.sub(r'\s*```$', '', content)
    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # 提取第一个 { ... } 块
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(content[start:end])
        raise


# ── Core functions ──────────────────────────────────────────────────────────────

async def get_next_question(
    conversation_history: List[Dict[str, str]],
    answers_count: int = 0,
) -> Dict[str, Any]:
    """
    基于对话历史，让 LLM 生成下一个问题。
    """
    llm = _make_llm()
    if llm is None:
        raise RuntimeError("OpenAI API Key not configured, dynamic mode unavailable")

    # 构造 LangChain messages
    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    for msg in conversation_history:
        if msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
        else:
            messages.append(HumanMessage(content=msg["content"]))

    if not conversation_history:
        messages.append(HumanMessage(content="你好，我想开始制作短视频，请问我。"))
    else:
        hint = (
            f"（系统提示：已回答 {answers_count} 个问题。"
            f"{'如果信息已足够生成创作简报，请将 is_complete 设为 true。' if answers_count >= 6 else '继续引导下一个关键维度。'}）"
        )
        messages.append(HumanMessage(content=hint))

    response = await llm.ainvoke(messages)
    return _parse_llm_json(response.content)


async def generate_brief_from_history(
    conversation_history: List[Dict[str, str]],
) -> Dict[str, Any]:
    """
    基于完整对话历史，让 LLM 提炼结构化 Brief JSON。
    """
    llm = _make_llm()
    if llm is None:
        raise RuntimeError("OpenAI API Key not configured")

    transcript_lines = []
    for msg in conversation_history:
        role_label = "顾问" if msg["role"] == "assistant" else "创作者"
        transcript_lines.append(f"{role_label}：{msg['content']}")
    transcript = "\n".join(transcript_lines)

    messages = [
        SystemMessage(content=BRIEF_SYSTEM_PROMPT),
        HumanMessage(content=f"以下是访谈对话记录：\n\n{transcript}"),
    ]

    response = await llm.ainvoke(messages)
    return _parse_llm_json(response.content)


def is_dynamic_mode_available() -> bool:
    """检查动态模式是否可用（API Key 已配置）"""
    return bool(settings.OPENAI_API_KEY)
