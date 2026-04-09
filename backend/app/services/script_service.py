from typing import Dict, Any, Optional
from openai import AsyncOpenAI
from app.config import settings

client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.OPENAI_BASE_URL,
)

SYSTEM_PROMPT = """You are a professional short video scriptwriter specializing in Douyin (TikTok) content.
Generate compelling voiceover scripts in Chinese based on the creator brief provided.
Return a valid JSON object with this structure:
{
  "title": "video title",
  "hook": "opening hook (first 3 seconds, must grab attention)",
  "sections": [
    {"id": 1, "title": "section name", "content": "voiceover text", "duration_estimate": "X seconds"}
  ],
  "cta": "call-to-action ending",
  "total_duration_estimate": "X seconds",
  "notes": "production notes for the creator"
}"""


async def generate_script(brief: Dict[str, Any]) -> Dict:
    user_prompt = f"""Please create a short video script based on this creator brief:

Topic Category: {brief.get('topic_category', 'N/A')}
Content Direction: {brief.get('content_direction', 'N/A')}
Target Audience: {brief.get('target_audience', 'N/A')}
Video Style: {brief.get('video_style', 'N/A')}
Target Duration: {brief.get('video_duration', 'N/A')}
Reference Accounts: {brief.get('reference_accounts', 'None')}
Special Requirements: {brief.get('special_requirements', 'None')}

Requirements:
1. Write the hook to immediately grab attention in the first 3 seconds
2. Structure the main body in clear sections matching the target duration
3. End with a strong CTA that encourages likes, follows, or comments
4. Write in a natural, conversational Chinese tone suitable for voiceover
5. Return only valid JSON, no markdown fences"""

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        response_format={"type": "json_object"},
    )

    import json
    content = response.choices[0].message.content
    return json.loads(content)


async def rewrite_section(section_content: str, instruction: str) -> str:
    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a professional short video scriptwriter. Rewrite the given section based on the instruction. Return only the rewritten text, no extra commentary."},
            {"role": "user", "content": f"Original:\n{section_content}\n\nInstruction: {instruction}"},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


REWRITE_SYSTEM_PROMPT = """\
你是一位专业的短视频口播文案改写专家。根据用户的改写指令，对指定段落进行精准改写。

【要求】
1. 只改写给定段落，不改动整体故事结构
2. 严格遵循改写指令（如：更幽默、更简短、更专业、加数据、换案例等）
3. 改写后语句自然流畅，适合真人口播
4. 如无特殊指令，保持与原文相近的字数（±20%）
5. 只返回改写后的段落文本，不加任何说明\
"""


async def rewrite_paragraph(
    script_content: Dict,
    paragraph_index: int,
    instruction: str,
) -> Dict[str, Any]:
    """
    对剧本 content.sections[paragraph_index] 进行 LLM 改写。

    Returns:
        {
            "paragraph_index": int,
            "original": str,          # 原始 content 字符串
            "rewritten": str,         # 改写后的文本
            "section_title": str,     # 段落标题
            "instruction": str,       # 用户指令
        }
    Raises:
        ValueError: paragraph_index 越界
        RuntimeError: LLM 调用失败
    """
    sections = script_content.get("sections", [])
    if not sections or paragraph_index < 0 or paragraph_index >= len(sections):
        raise ValueError(
            f"paragraph_index {paragraph_index} out of range "
            f"(sections count: {len(sections)})"
        )

    section = sections[paragraph_index]
    original_content = section.get("content", "")
    section_title = section.get("title", f"段落 {paragraph_index + 1}")

    # 附加上下文：标题 + 原文 + 全局简报（仅 hook + title，帮助 LLM 理解整体风格）
    context = (
        f"【视频标题】{script_content.get('title', '')}\n"
        f"【当前段落】{section_title}\n"
        f"【原文】\n{original_content}\n\n"
        f"【改写指令】{instruction}"
    )

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ],
        temperature=0.75,
        max_tokens=1024,
    )

    rewritten = response.choices[0].message.content.strip()

    return {
        "paragraph_index": paragraph_index,
        "original": original_content,
        "rewritten": rewritten,
        "section_title": section_title,
        "instruction": instruction,
    }


def apply_rewrite(script_content: Dict, paragraph_index: int, rewritten_text: str) -> Dict:
    """
    将改写后的文本应用到 script_content，返回新的 content dict（不修改原对象）。
    """
    import copy
    new_content = copy.deepcopy(script_content)
    sections = new_content.get("sections", [])
    if 0 <= paragraph_index < len(sections):
        sections[paragraph_index]["content"] = rewritten_text
    return new_content


# ── SSE 流式生成 ─────────────────────────────────────────────────────────────

async def generate_script_stream(brief: Dict[str, Any]):
    """
    流式生成剧本，逐 token yield 字符串。
    调用方负责将 token 拼接并在末尾解析 JSON。

    Yields:
        str  — 每个文本 token（data chunk）
        最后 yield "data: [DONE]\\n\\n" 表示结束
    """
    user_prompt = f"""Please create a short video script based on this creator brief:

Topic Category: {brief.get('topic_category', 'N/A')}
Content Direction: {brief.get('content_direction', 'N/A')}
Target Audience: {brief.get('target_audience', 'N/A')}
Video Style: {brief.get('video_style', 'N/A')}
Target Duration: {brief.get('video_duration', 'N/A')}
Reference Accounts: {brief.get('reference_accounts', 'None')}
Special Requirements: {brief.get('special_requirements', 'None')}

Requirements:
1. Write the hook to immediately grab attention in the first 3 seconds
2. Structure the main body in clear sections matching the target duration
3. End with a strong CTA that encourages likes, follows, or comments
4. Write in a natural, conversational Chinese tone suitable for voiceover
5. Return only valid JSON, no markdown fences"""

    stream = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        response_format={"type": "json_object"},
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


async def rewrite_paragraph_stream(
    script_content: Dict,
    paragraph_index: int,
    instruction: str,
):
    """
    流式改写指定段落。

    Yields:
        str  — 每个文本 token
    Raises:
        ValueError: paragraph_index 越界
    """
    sections = script_content.get("sections", [])
    if not sections or paragraph_index < 0 or paragraph_index >= len(sections):
        raise ValueError(
            f"paragraph_index {paragraph_index} out of range "
            f"(sections count: {len(sections)})"
        )

    section = sections[paragraph_index]
    original_content = section.get("content", "")
    section_title = section.get("title", f"段落 {paragraph_index + 1}")

    context = (
        f"【视频标题】{script_content.get('title', '')}\n"
        f"【当前段落】{section_title}\n"
        f"【原文】\n{original_content}\n\n"
        f"【改写指令】{instruction}"
    )

    stream = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ],
        temperature=0.75,
        max_tokens=1024,
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
