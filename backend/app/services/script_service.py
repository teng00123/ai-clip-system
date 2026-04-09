from typing import Dict, Any
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
