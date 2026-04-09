from typing import Dict, Any, Optional, Literal
from openai import AsyncOpenAI
from app.config import settings

client = AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.OPENAI_BASE_URL,
)

# 支持的剧本格式
ScriptFormat = Literal["voiceover", "storyboard"]

SYSTEM_PROMPT = """You are a professional short video scriptwriter specializing in Douyin (TikTok) content.
Generate compelling voiceover scripts in Chinese based on the creator brief provided.
Return a valid JSON object with this structure:
{
  "title": "视频标题",
  "hook": "开局鑂子（前3秒，必须抓住注意力）",
  "sections": [
    {"id": 1, "title": "段落名称", "content": "口播文案", "duration_estimate": "X seconds"}
  ],
  "cta": "结尾引导行动",
  "total_duration_estimate": "X seconds",
  "notes": "制作备注"
}"""

STORYBOARD_SYSTEM_PROMPT = """You are a professional short video director and scriptwriter specializing in Douyin (TikTok) content.
Generate a detailed storyboard script in Chinese based on the creator brief provided.
Return a valid JSON object with this structure:
{
  "title": "视频标题",
  "hook": "开局鑂子描述（前3秒画面）",
  "sections": [
    {
      "id": 1,
      "title": "分镜标题",
      "shot_type": "景别类型，如：特写/近景/中景/全景/信息图/过渡",
      "visual": "画面内容描述（场景、动作、构图）",
      "voiceover": "同期口播文案",
      "caption": "字幕/花字文案（可为空）",
      "duration_estimate": "X seconds"
    }
  ],
  "cta": "结尾引导行动",
  "total_duration_estimate": "X seconds",
  "notes": "拍摄和制作备注"
}"""


def _build_brief_prompt(brief: Dict[str, Any]) -> str:
    """Build common brief section used by both voiceover and storyboard prompts."""
    return f"""Creator Brief:

Topic Category: {brief.get('topic_category', 'N/A')}
Content Direction: {brief.get('content_direction', 'N/A')}
Target Audience: {brief.get('target_audience', 'N/A')}
Video Style: {brief.get('video_style', 'N/A')}
Target Duration: {brief.get('video_duration', 'N/A')}
Tone: {brief.get('tone', 'N/A')}
Reference Accounts: {brief.get('reference_accounts', 'None')}
Special Requirements: {brief.get('special_requirements', 'None')}
"""


async def generate_script(brief: Dict[str, Any], fmt: ScriptFormat = "voiceover") -> Dict:
    if fmt == "storyboard":
        return await _generate_storyboard(brief)
    return await _generate_voiceover(brief)


async def _generate_voiceover(brief: Dict[str, Any]) -> Dict:
    user_prompt = _build_brief_prompt(brief) + """
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


async def _generate_storyboard(brief: Dict[str, Any]) -> Dict:
    user_prompt = _build_brief_prompt(brief) + """
Requirements:
1. Write an eye-catching visual hook for the first 3 seconds
2. Break down each scene with shot type, visual description, and matching voiceover
3. Include appropriate captions/text overlays for key moments
4. End with a compelling CTA
5. Return only valid JSON, no markdown fences"""

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": STORYBOARD_SYSTEM_PROMPT},
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

async def generate_script_stream(brief: Dict[str, Any], fmt: ScriptFormat = "voiceover"):
    """
    流式生成剧本，逐 token yield 字符串。
    fmt: 'voiceover'(口播) 或 'storyboard'(分镜)
    """
    if fmt == "storyboard":
        system = STORYBOARD_SYSTEM_PROMPT
        extra = (
            "\nRequirements:\n"
            "1. Write an eye-catching visual hook for the first 3 seconds\n"
            "2. Break down each scene with shot type, visual description, and matching voiceover\n"
            "3. Include appropriate captions/text overlays for key moments\n"
            "4. End with a compelling CTA\n"
            "5. Return only valid JSON, no markdown fences"
        )
    else:
        system = SYSTEM_PROMPT
        extra = (
            "\nRequirements:\n"
            "1. Write the hook to immediately grab attention in the first 3 seconds\n"
            "2. Structure the main body in clear sections matching the target duration\n"
            "3. End with a strong CTA that encourages likes, follows, or comments\n"
            "4. Write in a natural, conversational Chinese tone suitable for voiceover\n"
            "5. Return only valid JSON, no markdown fences"
        )

    user_prompt = _build_brief_prompt(brief) + extra

    stream = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
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
