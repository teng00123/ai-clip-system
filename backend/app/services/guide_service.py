from typing import List, Dict, Any, Optional


QUESTIONS = [
    {
        "question_text": "视频主题/定位",
        "display": "你想创作哪个方向的视频？你的内容定位是什么？",
        "question_type": "single_choice",
        "options": [
            "知识分享 / 技能教程",
            "生活记录 / 日常 Vlog",
            "产品测评 / 好物推荐",
            "娱乐 / 搞笑",
            "美食 / 旅行",
            "健身 / 健康",
            "其他（下一步详细说明）",
        ],
    },
    {
        "question_text": "内容方向详述",
        "display": "请用一句话描述你的内容方向（例如：教年轻人如何高效管理时间）",
        "question_type": "text_input",
        "options": None,
    },
    {
        "question_text": "目标受众",
        "display": "你的目标受众是哪些人？",
        "question_type": "single_choice",
        "options": [
            "学生群体（18-22岁）",
            "职场新人（22-30岁）",
            "上班族（30-40岁）",
            "宝妈 / 家庭受众",
            "创业者 / 商务人士",
            "大众人群，无特定目标",
        ],
    },
    {
        "question_text": "视频风格 / 调性",
        "display": "你希望视频呈现什么样的风格和调性？",
        "question_type": "single_choice",
        "options": [
            "活泼 / 快节奏 / 潮流感",
            "沉稳 / 真诚 / 故事感",
            "专业 / 权威 / 干货满满",
            "幽默 / 轻松 / 有趣",
            "励志 / 正能量 / 情感共鸣",
        ],
    },
    {
        "question_text": "单个视频时长",
        "display": "你希望每条视频的时长是多少？",
        "question_type": "single_choice",
        "options": [
            "30秒以内（极短，高能量）",
            "30秒 - 1分钟（标准短视频）",
            "1-3分钟（中等时长）",
            "3-5分钟（深度内容）",
        ],
    },
    {
        "question_text": "发布频率",
        "display": "你计划以什么频率更新发布？",
        "question_type": "single_choice",
        "options": [
            "每天更新",
            "每周3-5条",
            "每周1-2条",
            "每月2-4条",
            "不定期，以内容质量为准",
        ],
    },
    {
        "question_text": "参考账号",
        "display": "你有没有喜欢的抖音/社交媒体参考账号？（选填，填写账号名或描述其风格）",
        "question_type": "text_input",
        "options": None,
    },
    {
        "question_text": "特殊要求或备注",
        "display": "还有其他特殊要求或备注吗？（例如：必须出镜、不要背景音乐、特定色调等）",
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
            f"内容类型：{answers.get('0', '未填写')}。"
            f"方向：{answers.get('1', '未填写')}。"
            f"受众：{answers.get('2', '未填写')}。"
            f"风格：{answers.get('3', '未填写')}。"
            f"时长：{answers.get('4', '未填写')}。"
        ),
    }
    return brief
