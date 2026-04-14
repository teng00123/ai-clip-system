"""
script_service.py

使用 LangChain + ChatOpenAI 实现剧本生成与改写。
兼容 gpt-3.5-turbo 等不支持 response_format=json_object 的模型，
通过 JsonOutputParser / StrOutputParser 处理输出。
"""

import json
import copy
from typing import Dict, Any, Literal, AsyncIterator

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser

from app.config import settings

ScriptFormat = Literal["voiceover", "storyboard"]

# ── LLM 实例 ─────────────────────────────────────────────────────────────────

def _make_llm(streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        temperature=0.7,
        streaming=streaming,
    )


# ── Prompts ──────────────────────────────────────────────────────────────────

VOICEOVER_SYSTEM = """你是一位专业的短视频口播文案撰写专家，专注于抖音/TikTok内容创作。
请根据创作简报生成口播剧本，严格返回如下 JSON 格式（不要加 markdown 代码块）：
{{
  "title": "视频标题",
  "hook": "开局钩子（前3秒，必须抓住注意力）",
  "sections": [
    {{"id": 1, "title": "段落名称", "content": "口播文案", "duration_estimate": "X seconds"}}
  ],
  "cta": "结尾引导行动",
  "total_duration_estimate": "X seconds",
  "notes": "制作备注"
}}"""

STORYBOARD_SYSTEM = """你是一位专业的短视频导演和分镜脚本撰写专家，专注于抖音/TikTok内容创作。
请根据创作简报生成分镜剧本，严格返回如下 JSON 格式（不要加 markdown 代码块）：
{{
  "title": "视频标题",
  "hook": "开局钩子描述（前3秒画面）",
  "sections": [
    {{
      "id": 1,
      "title": "分镜标题",
      "shot_type": "景别类型，如：特写/近景/中景/全景",
      "visual": "画面内容描述（场景、动作、构图）",
      "voiceover": "同期口播文案",
      "caption": "字幕/花字文案（可为空）",
      "duration_estimate": "X seconds"
    }}
  ],
  "cta": "结尾引导行动",
  "total_duration_estimate": "X seconds",
  "notes": "拍摄和制作备注"
}}"""

VOICEOVER_REQUIREMENTS = """
要求：
1. 开局钩子必须在前3秒抓住观众注意力
2. 按目标时长合理拆分正文段落
3. 结尾CTA引导点赞/关注/评论
4. 语言自然口语化，适合真人口播
5. 只返回 JSON，不要加任何说明或 markdown"""

STORYBOARD_REQUIREMENTS = """
要求：
1. 开局画面必须在前3秒吸引眼球
2. 每个分镜包含景别、画面描述和同期口播
3. 关键信息点加字幕/花字
4. 结尾CTA有力
5. 只返回 JSON，不要加任何说明或 markdown"""

REWRITE_SYSTEM = """\
你是一位专业的短视频口播文案改写专家。根据改写指令对指定段落进行精准改写。

要求：
1. 只改写给定段落，不改动整体故事结构
2. 严格遵循改写指令（如：更幽默、更简短、更专业、加数据、换案例等）
3. 改写后语句自然流畅，适合真人口播
4. 如无特殊指令，保持与原文相近的字数（±20%）
5. 只返回改写后的段落文本，不加任何说明"""


def _build_brief_text(brief: Dict[str, Any]) -> str:
    return (
        f"创作简报：\n\n"
        f"内容方向：{brief.get('topic_category', 'N/A')}\n"
        f"具体选题：{brief.get('content_direction', 'N/A')}\n"
        f"目标受众：{brief.get('target_audience', 'N/A')}\n"
        f"视频风格：{brief.get('video_style', 'N/A')}\n"
        f"目标时长：{brief.get('video_duration', 'N/A')}\n"
        f"语言风格：{brief.get('tone', 'N/A')}\n"
        f"参考账号：{brief.get('reference_accounts', '无')}\n"
        f"特殊要求：{brief.get('special_requirements', '无')}\n"
    )


# ── 非流式生成 ────────────────────────────────────────────────────────────────

async def generate_script(brief: Dict[str, Any], fmt: ScriptFormat = "voiceover") -> Dict:
    system = VOICEOVER_SYSTEM if fmt == "voiceover" else STORYBOARD_SYSTEM
    requirements = VOICEOVER_REQUIREMENTS if fmt == "voiceover" else STORYBOARD_REQUIREMENTS

    prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        ("human", "{brief}{requirements}"),
    ])

    llm = _make_llm(streaming=False)
    chain = prompt | llm | StrOutputParser()

    raw = await chain.ainvoke({
        "brief": _build_brief_text(brief),
        "requirements": requirements,
    })

    # 提取 JSON（兼容模型在输出前后添加说明文字的情况）
    return _extract_json(raw)


# ── 流式生成 ──────────────────────────────────────────────────────────────────

async def generate_script_stream(
    brief: Dict[str, Any], fmt: ScriptFormat = "voiceover"
) -> AsyncIterator[str]:
    """逐 token yield，供 SSE 接口使用。"""
    system = VOICEOVER_SYSTEM if fmt == "voiceover" else STORYBOARD_SYSTEM
    requirements = VOICEOVER_REQUIREMENTS if fmt == "voiceover" else STORYBOARD_REQUIREMENTS

    prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        ("human", "{brief}{requirements}"),
    ])

    llm = _make_llm(streaming=True)
    chain = prompt | llm | StrOutputParser()

    async for token in chain.astream({
        "brief": _build_brief_text(brief),
        "requirements": requirements,
    }):
        yield token


# ── 段落改写（非流式）────────────────────────────────────────────────────────

async def rewrite_paragraph(
    script_content: Dict,
    paragraph_index: int,
    instruction: str,
) -> Dict[str, Any]:
    sections = script_content.get("sections", [])
    if not sections or paragraph_index < 0 or paragraph_index >= len(sections):
        raise ValueError(
            f"paragraph_index {paragraph_index} out of range "
            f"(sections count: {len(sections)})"
        )

    section = sections[paragraph_index]
    original_content = section.get("content", "")
    section_title = section.get("title", f"段落 {paragraph_index + 1}")

    prompt = ChatPromptTemplate.from_messages([
        ("system", REWRITE_SYSTEM),
        ("human", (
            "【视频标题】{title}\n"
            "【当前段落】{section_title}\n"
            "【原文】\n{original}\n\n"
            "【改写指令】{instruction}"
        )),
    ])

    llm = _make_llm(streaming=False)
    chain = prompt | llm | StrOutputParser()

    rewritten = await chain.ainvoke({
        "title": script_content.get("title", ""),
        "section_title": section_title,
        "original": original_content,
        "instruction": instruction,
    })

    return {
        "paragraph_index": paragraph_index,
        "original": original_content,
        "rewritten": rewritten.strip(),
        "section_title": section_title,
        "instruction": instruction,
    }


# ── 段落改写（流式）──────────────────────────────────────────────────────────

async def rewrite_paragraph_stream(
    script_content: Dict,
    paragraph_index: int,
    instruction: str,
) -> AsyncIterator[str]:
    sections = script_content.get("sections", [])
    if not sections or paragraph_index < 0 or paragraph_index >= len(sections):
        raise ValueError(
            f"paragraph_index {paragraph_index} out of range "
            f"(sections count: {len(sections)})"
        )

    section = sections[paragraph_index]
    original_content = section.get("content", "")
    section_title = section.get("title", f"段落 {paragraph_index + 1}")

    prompt = ChatPromptTemplate.from_messages([
        ("system", REWRITE_SYSTEM),
        ("human", (
            "【视频标题】{title}\n"
            "【当前段落】{section_title}\n"
            "【原文】\n{original}\n\n"
            "【改写指令】{instruction}"
        )),
    ])

    llm = _make_llm(streaming=True)
    chain = prompt | llm | StrOutputParser()

    async for token in chain.astream({
        "title": script_content.get("title", ""),
        "section_title": section_title,
        "original": original_content,
        "instruction": instruction,
    }):
        yield token


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> Dict:
    """
    从模型输出中提取 JSON，兼容：
    - 纯 JSON 输出
    - ```json ... ``` 包裹
    - 前后有说明文字
    """
    text = text.strip()

    # 去掉 markdown 代码块
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()

    # 直接尝试解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 提取第一个 { ... } 块
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"无法从模型输出中解析 JSON：{text[:200]}")


def apply_rewrite(script_content: Dict, paragraph_index: int, rewritten_text: str) -> Dict:
    """将改写后的文本写入 content，返回新 dict（不修改原对象）。"""
    new_content = copy.deepcopy(script_content)
    sections = new_content.get("sections", [])
    if 0 <= paragraph_index < len(sections):
        sections[paragraph_index]["content"] = rewritten_text
    return new_content


# ── 兼容旧接口（保留给其他模块引用）────────────────────────────────────────

async def rewrite_section(section_content: str, instruction: str) -> str:
    """旧版自由文本改写接口，保持向后兼容。"""
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一位专业的短视频文案改写专家。根据指令改写给定内容，只返回改写后的文本。"),
        ("human", "原文：\n{content}\n\n改写指令：{instruction}"),
    ])
    llm = _make_llm(streaming=False)
    chain = prompt | llm | StrOutputParser()
    result = await chain.ainvoke({"content": section_content, "instruction": instruction})
    return result.strip()
