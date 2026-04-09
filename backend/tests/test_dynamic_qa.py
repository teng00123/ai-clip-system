"""
tests/test_dynamic_qa.py — 动态问答引擎测试

测试策略：
- 所有 OpenAI API 调用全部 mock（不发真实网络请求）
- 验证对话历史正确累积
- 验证 is_complete 触发后 brief 生成正确
- 验证 API Key 缺失时返回 503（降级行为）
- 验证静态模式端点仍完整可用（向后兼容）

注意：E2E 部分使用同步 TestClient（与 test_e2e.py 风格一致）
      Service 单元测试使用 async（直接调用 async 函数）
"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.guide_service import TOTAL_STEPS


# ── Helpers ────────────────────────────────────────────────────────────────────

def _register(client, email="dqa@example.com", password="pw123456"):
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _auth(client, email="dqa@example.com", password="pw123456"):
    tok = _register(client, email, password)["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _create_project(client, headers, name="DQA Project"):
    r = client.post("/api/projects", json={"name": name, "description": "test"}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def make_openai_response(content: dict) -> MagicMock:
    """构造 openai.chat.completions.create 的 mock 返回值"""
    msg = MagicMock()
    msg.content = json.dumps(content)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ── Fixtures ───────────────────────────────────────────────────────────────────

LLM_QUESTION_1 = {
    "question": "你想制作什么类型的短视频？",
    "question_type": "single_choice",
    "options": ["知识分享", "生活 vlog", "产品测评", "搞笑娱乐"],
    "is_complete": False,
}

LLM_QUESTION_2 = {
    "question": "你的目标受众主要是哪个群体？",
    "question_type": "single_choice",
    "options": ["学生党", "职场新人", "宝妈宝爸", "创业者"],
    "is_complete": False,
}

LLM_COMPLETE = {
    "question": "",
    "question_type": "text_input",
    "options": None,
    "is_complete": True,
}

MOCK_BRIEF = {
    "topic_category": "知识分享",
    "content_direction": "帮助职场新人提升工作效率",
    "target_audience": "职场新人（22-30岁）",
    "video_style": "专业权威",
    "video_duration": "1-3分钟",
    "publish_frequency": "",
    "reference_accounts": "",
    "special_requirements": "",
    "summary": "面向职场新人的效率提升知识分享视频，专业权威风格，每期1-3分钟。",
}


# ── Tests: mode endpoint ───────────────────────────────────────────────────────

def test_mode_endpoint_no_key(client):
    """无 API Key 时，mode 端点返回 static"""
    headers = _auth(client, "mode-nokey@test.com")
    pid = _create_project(client, headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=False):
        resp = client.get(f"/api/guide/{pid}/mode", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["dynamic_available"] is False
    assert data["recommended_mode"] == "static"


def test_mode_endpoint_with_key(client):
    """有 API Key 时，mode 端点返回 dynamic"""
    headers = _auth(client, "mode-withkey@test.com")
    pid = _create_project(client, headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=True):
        resp = client.get(f"/api/guide/{pid}/mode", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["dynamic_available"] is True
    assert data["recommended_mode"] == "dynamic"


# ── Tests: dynamic/start ───────────────────────────────────────────────────────

def test_dynamic_start_no_key_returns_503(client):
    """无 API Key 时调用 dynamic/start 返回 503"""
    headers = _auth(client, "dstart-nokey@test.com")
    pid = _create_project(client, headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=False):
        resp = client.post(f"/api/guide/{pid}/dynamic/start", headers=headers)

    assert resp.status_code == 503
    assert "OPENAI_API_KEY" in resp.json()["detail"]


def test_dynamic_start_returns_first_question(client):
    """dynamic/start 成功调用 LLM，返回第一个问题"""
    headers = _auth(client, "dstart-ok@test.com")
    pid = _create_project(client, headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         patch("app.services.dynamic_qa_service.get_client") as mock_get_client:

        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(
            return_value=make_openai_response(LLM_QUESTION_1)
        )
        mock_get_client.return_value = mock_llm

        resp = client.post(f"/api/guide/{pid}/dynamic/start", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["question"] == "你想制作什么类型的短视频？"
    assert data["question_type"] == "single_choice"
    assert len(data["options"]) == 4
    assert data["is_complete"] is False
    assert data["mode"] == "dynamic"


def test_dynamic_start_llm_error_returns_502(client):
    """LLM 调用异常时返回 502"""
    headers = _auth(client, "dstart-err@test.com")
    pid = _create_project(client, headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         patch("app.services.dynamic_qa_service.get_client") as mock_get_client:

        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(side_effect=Exception("API timeout"))
        mock_get_client.return_value = mock_llm

        resp = client.post(f"/api/guide/{pid}/dynamic/start", headers=headers)

    assert resp.status_code == 502
    assert "LLM error" in resp.json()["detail"]


# ── Tests: dynamic/answer ──────────────────────────────────────────────────────

def test_dynamic_answer_advances_conversation(client):
    """提交回答后对话历史累积，LLM 返回下一问题"""
    headers = _auth(client, "danswer-ok@test.com")
    pid = _create_project(client, headers)

    # start
    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         patch("app.services.dynamic_qa_service.get_client") as mock_get_client:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(
            return_value=make_openai_response(LLM_QUESTION_1)
        )
        mock_get_client.return_value = mock_llm
        client.post(f"/api/guide/{pid}/dynamic/start", headers=headers)

    # answer → next question
    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         patch("app.services.dynamic_qa_service.get_client") as mock_get_client:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(
            return_value=make_openai_response(LLM_QUESTION_2)
        )
        mock_get_client.return_value = mock_llm
        resp = client.post(
            f"/api/guide/{pid}/dynamic/answer",
            json={"answer": "知识分享"},
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["question"] == "你的目标受众主要是哪个群体？"
    assert data["is_complete"] is False
    assert data["answers_count"] == 1


def test_dynamic_answer_complete_generates_brief(client):
    """LLM 返回 is_complete=True 时自动生成 Brief，会话标记完成"""
    headers = _auth(client, "dcomplete@test.com")
    pid = _create_project(client, headers)

    # start
    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         patch("app.services.dynamic_qa_service.get_client") as mock_get_client:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(
            return_value=make_openai_response(LLM_QUESTION_1)
        )
        mock_get_client.return_value = mock_llm
        client.post(f"/api/guide/{pid}/dynamic/start", headers=headers)

    # answer → is_complete
    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         patch("app.services.dynamic_qa_service.get_client") as mock_get_client, \
         patch("app.api.guide.generate_brief_from_history", new_callable=AsyncMock) as mock_brief_fn:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(
            return_value=make_openai_response(LLM_COMPLETE)
        )
        mock_get_client.return_value = mock_llm
        mock_brief_fn.return_value = MOCK_BRIEF

        resp = client.post(
            f"/api/guide/{pid}/dynamic/answer",
            json={"answer": "职场新人"},
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["is_complete"] is True
    assert resp.json()["question"] == ""

    # brief 可访问
    brief_resp = client.get(f"/api/guide/{pid}/brief", headers=headers)
    assert brief_resp.status_code == 200
    brief = brief_resp.json()
    assert brief["topic_category"] == "知识分享"
    assert "summary" in brief


def test_dynamic_answer_after_complete_returns_400(client):
    """已完成的会话再次提交答案返回 400"""
    headers = _auth(client, "dalreadydone@test.com")
    pid = _create_project(client, headers)

    # 先完成
    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         patch("app.services.dynamic_qa_service.get_client") as mock_get_client:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(
            return_value=make_openai_response(LLM_QUESTION_1)
        )
        mock_get_client.return_value = mock_llm
        client.post(f"/api/guide/{pid}/dynamic/start", headers=headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         patch("app.services.dynamic_qa_service.get_client") as mock_get_client, \
         patch("app.api.guide.generate_brief_from_history", new_callable=AsyncMock) as mock_brief_fn:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(
            return_value=make_openai_response(LLM_COMPLETE)
        )
        mock_get_client.return_value = mock_llm
        mock_brief_fn.return_value = MOCK_BRIEF
        client.post(f"/api/guide/{pid}/dynamic/answer", json={"answer": "x"}, headers=headers)

    # 再提交
    with patch("app.api.guide.is_dynamic_mode_available", return_value=True):
        resp = client.post(
            f"/api/guide/{pid}/dynamic/answer",
            json={"answer": "再提交"},
            headers=headers,
        )
    assert resp.status_code == 400
    assert "completed" in resp.json()["detail"]


def test_dynamic_answer_no_key_returns_503(client):
    """无 API Key 时提交动态答案返回 503"""
    headers = _auth(client, "danswer-nokey@test.com")
    pid = _create_project(client, headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=False):
        resp = client.post(
            f"/api/guide/{pid}/dynamic/answer",
            json={"answer": "测试"},
            headers=headers,
        )
    assert resp.status_code == 503


# ── Tests: static mode backward compat ────────────────────────────────────────

def test_static_question_still_works(client):
    """静态模式 GET /question 端点不受影响"""
    headers = _auth(client, "static-compat@test.com")
    pid = _create_project(client, headers)
    # 需要先 start
    client.post(f"/api/guide/{pid}/start", headers=headers)

    resp = client.get(f"/api/guide/{pid}/question", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "question_text" in data
    assert data["step"] == 0
    assert data["total_steps"] == TOTAL_STEPS
    assert data["is_dynamic"] is False


def test_static_full_flow_still_works(client):
    """静态模式完整 8 步流程不受影响"""
    headers = _auth(client, "static-full@test.com")
    pid = _create_project(client, headers)
    client.post(f"/api/guide/{pid}/start", headers=headers)

    answers = [
        "Knowledge sharing / Skills tutorial",
        "Help young professionals improve productivity",
        "Young professionals (22-30)",
        "Professional / Authoritative / Informative",
        "1-3 minutes (medium length)",
        "1-2 times per week",
        "",
        "",
    ]
    for i, answer in enumerate(answers):
        resp = client.post(
            f"/api/guide/{pid}/answer",
            json={"step": i, "answer": answer},
            headers=headers,
        )
        assert resp.status_code == 200, f"step {i} failed: {resp.text}"

    brief_resp = client.get(f"/api/guide/{pid}/brief", headers=headers)
    assert brief_resp.status_code == 200
    brief = brief_resp.json()
    assert brief["topic_category"] == "Knowledge sharing / Skills tutorial"
    assert "summary" in brief


def test_brief_before_complete_returns_400(client):
    """未完成的会话获取 brief 返回 400"""
    headers = _auth(client, "brief-incomplete@test.com")
    pid = _create_project(client, headers)
    client.post(f"/api/guide/{pid}/start", headers=headers)

    resp = client.get(f"/api/guide/{pid}/brief", headers=headers)
    assert resp.status_code == 400


# ── Service unit tests (async, direct function calls) ─────────────────────────

async def test_get_next_question_no_history():
    """无对话历史时，首次提问构造正确"""
    from app.services.dynamic_qa_service import get_next_question

    with patch("app.services.dynamic_qa_service.get_client") as mock_get_client:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(
            return_value=make_openai_response(LLM_QUESTION_1)
        )
        mock_get_client.return_value = mock_llm
        result = await get_next_question([], answers_count=0)

    assert result["question"] == "你想制作什么类型的短视频？"
    assert result["is_complete"] is False

    call_args = mock_llm.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"


async def test_get_next_question_with_history():
    """有对话历史时，消息列表正确包含历史"""
    from app.services.dynamic_qa_service import get_next_question

    history = [
        {"role": "assistant", "content": "你想制作什么类型的短视频？"},
        {"role": "user", "content": "知识分享"},
    ]

    with patch("app.services.dynamic_qa_service.get_client") as mock_get_client:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(
            return_value=make_openai_response(LLM_QUESTION_2)
        )
        mock_get_client.return_value = mock_llm
        result = await get_next_question(history, answers_count=1)

    call_args = mock_llm.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    # system + history[0] + history[1] + progress hint
    assert len(messages) >= 4
    user_messages = [m for m in messages if m["role"] == "user"]
    assert any("知识分享" == m["content"] for m in user_messages)


async def test_get_next_question_no_client_raises():
    """API Key 缺失时抛出 RuntimeError"""
    from app.services.dynamic_qa_service import get_next_question

    with patch("app.services.dynamic_qa_service.get_client", return_value=None):
        with pytest.raises(RuntimeError, match="OpenAI API Key"):
            await get_next_question([], answers_count=0)


async def test_generate_brief_from_history():
    """generate_brief_from_history 正确构造 transcript 并解析 LLM 返回"""
    from app.services.dynamic_qa_service import generate_brief_from_history

    history = [
        {"role": "assistant", "content": "你想制作什么类型的短视频？"},
        {"role": "user", "content": "知识分享"},
        {"role": "assistant", "content": "你的目标受众是谁？"},
        {"role": "user", "content": "职场新人"},
    ]

    with patch("app.services.dynamic_qa_service.get_client") as mock_get_client:
        mock_llm = AsyncMock()
        mock_llm.chat.completions.create = AsyncMock(
            return_value=make_openai_response(MOCK_BRIEF)
        )
        mock_get_client.return_value = mock_llm
        result = await generate_brief_from_history(history)

    assert result["topic_category"] == "知识分享"
    assert "summary" in result

    # transcript 应包含角色标签
    call_args = mock_llm.chat.completions.create.call_args
    user_msg = next(m for m in call_args.kwargs["messages"] if m["role"] == "user")
    assert "顾问" in user_msg["content"]
    assert "创作者" in user_msg["content"]


async def test_parse_llm_json_handles_markdown_fence():
    """_parse_llm_json 容错处理带 markdown fence 的返回"""
    from app.services.dynamic_qa_service import _parse_llm_json

    raw = '```json\n{"key": "value"}\n```'
    assert _parse_llm_json(raw) == {"key": "value"}


async def test_parse_llm_json_handles_plain():
    """_parse_llm_json 处理纯 JSON 字符串"""
    from app.services.dynamic_qa_service import _parse_llm_json

    raw = '{"question": "hello", "is_complete": false}'
    result = _parse_llm_json(raw)
    assert result["question"] == "hello"
    assert result["is_complete"] is False


async def test_is_dynamic_mode_available_true():
    from app.services.dynamic_qa_service import is_dynamic_mode_available
    with patch("app.services.dynamic_qa_service.settings") as s:
        s.OPENAI_API_KEY = "sk-xxx"
        assert is_dynamic_mode_available() is True


async def test_is_dynamic_mode_available_false():
    from app.services.dynamic_qa_service import is_dynamic_mode_available
    with patch("app.services.dynamic_qa_service.settings") as s:
        s.OPENAI_API_KEY = ""
        assert is_dynamic_mode_available() is False
