from typing import List, Dict, Any, Optional


QUESTIONS = [
    {
        "question_text": "your video's main topic/positioning?",
        "display": "You want to create videos about what topic? What is your positioning?",
        "question_type": "single_choice",
        "options": [
            "Knowledge sharing / Skills tutorial",
            "Life vlog / Daily routine",
            "Product review / Evaluation",
            "Entertainment / Comedy",
            "Food / Travel",
            "Fitness / Health",
            "Other (please specify in next step)",
        ],
    },
    {
        "question_text": "describe your content direction in detail",
        "display": "Please describe your content direction in one sentence (e.g.: teach young people how to manage time efficiently)",
        "question_type": "text_input",
        "options": None,
    },
    {
        "question_text": "target audience",
        "display": "Who is your target audience?",
        "question_type": "single_choice",
        "options": [
            "Students (18-22)",
            "Young professionals (22-30)",
            "Working adults (30-40)",
            "Parents / Family audience",
            "Entrepreneurs / Business people",
            "General public, no specific target",
        ],
    },
    {
        "question_text": "video style / tone",
        "display": "What style and tone do you want for your videos?",
        "question_type": "single_choice",
        "options": [
            "Energetic / Fast-paced / Trendy",
            "Calm / Sincere / Story-driven",
            "Professional / Authoritative / Informative",
            "Humorous / Relaxed / Fun",
            "Inspirational / Motivational / Emotional",
        ],
    },
    {
        "question_text": "single video duration",
        "display": "How long do you want each video to be?",
        "question_type": "single_choice",
        "options": [
            "Under 30 seconds (very short, high energy)",
            "30 seconds - 1 minute (standard short video)",
            "1-3 minutes (medium length)",
            "3-5 minutes (in-depth content)",
        ],
    },
    {
        "question_text": "publishing frequency",
        "display": "How frequently do you plan to publish?",
        "question_type": "single_choice",
        "options": [
            "Daily",
            "3-5 times per week",
            "1-2 times per week",
            "2-4 times per month",
            "Irregular, depending on content quality",
        ],
    },
    {
        "question_text": "reference accounts",
        "display": "Do you have any reference Douyin/social media accounts you admire? (Optional, enter account name or describe their style)",
        "question_type": "text_input",
        "options": None,
    },
    {
        "question_text": "special requirements or notes",
        "display": "Any other special requirements or notes? (e.g.: must include face cam, no background music, specific color tone, etc.)",
        "question_type": "text_input",
        "options": None,
    },
]

TOTAL_STEPS = len(QUESTIONS)


def get_question(step: int) -> Optional[Dict]:
    if step < 0 or step >= TOTAL_STEPS:
        return None
    q = QUESTIONS[step].copy()
    q["step"] = step
    q["total_steps"] = TOTAL_STEPS
    return q


def generate_brief(answers: Dict[str, Any]) -> Dict:
    brief = {
        "topic_category": answers.get("0", ""),
        "content_direction": answers.get("1", ""),
        "target_audience": answers.get("2", ""),
        "video_style": answers.get("3", ""),
        "video_duration": answers.get("4", ""),
        "publish_frequency": answers.get("5", ""),
        "reference_accounts": answers.get("6", ""),
        "special_requirements": answers.get("7", ""),
        "summary": (
            f"Content type: {answers.get('0', 'N/A')}. "
            f"Direction: {answers.get('1', 'N/A')}. "
            f"Audience: {answers.get('2', 'N/A')}. "
            f"Style: {answers.get('3', 'N/A')}. "
            f"Duration: {answers.get('4', 'N/A')}."
        ),
    }
    return brief
