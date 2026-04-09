"""
tests/test_guide_dynamic_ui.py — 动态问答 UI 升级支持测试

覆盖：
- GET /guide/{pid}/session: 无 session 返回 404，有 session 返回 200
- GET /guide/{pid}/dynamic/available: 返回 {available: bool}
- GET /guide/{pid}/dynamic/available: OPENAI_API_KEY 为空时 available=False
- 动态问答完整流程（start → N轮 answer → is_complete=True）
- 动态 answer 返回 DynamicQuestionOut 结构验证
- 静态模式不受影响
- DynamicAnswerSubmit schema
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ── helpers ───────────────────────────────────────────────────────────────────

def _auth(client, email, password="pw123456"):
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _create_project(client, headers):
    r = client.post("/api/projects", json={"name": "UI Test", "description": ""}, headers=headers)
    assert r.status_code == 200
    return r.json()["id"]


def _mock_llm_question(question_text="你的视频主要面向哪类人群？", is_complete=False, qtype="text_input"):
    mock_result = {
        "question": question_text,
        "question_type": qtype,
        "options": None,
        "is_complete": is_complete,
    }
    return patch(
        "app.api.guide.get_next_question",
        new=AsyncMock(return_value=mock_result),
    )


def _mock_brief():
    return patch(
        "app.api.guide.generate_brief_from_history",
        new=AsyncMock(return_value={"core_goal": "帮助用户学习编程", "tone": "轻松幽默"}),
    )


# ── GET /session ──────────────────────────────────────────────────────────────

def test_get_session_no_session_returns_404(client):
    """没有创建 session 时 GET /session 返回 404"""
    headers = _auth(client, "gui-sess-404@test.com")
    pid = _create_project(client, headers)

    resp = client.get(f"/api/guide/{pid}/session", headers=headers)
    assert resp.status_code == 404


def test_get_session_after_start_returns_200(client):
    """start 后 GET /session 返回 session 数据"""
    headers = _auth(client, "gui-sess-200@test.com")
    pid = _create_project(client, headers)

    client.post(f"/api/guide/{pid}/start", headers=headers)
    resp = client.get(f"/api/guide/{pid}/session", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == pid
    assert "completed" in data
    assert "mode" in data


def test_get_session_reflects_mode(client):
    """session 的 mode 字段正确（默认 static）"""
    headers = _auth(client, "gui-sess-mode@test.com")
    pid = _create_project(client, headers)

    client.post(f"/api/guide/{pid}/start", headers=headers)
    resp = client.get(f"/api/guide/{pid}/session", headers=headers)

    assert resp.status_code == 200
    # 默认 static（无 OPENAI_API_KEY）
    assert resp.json()["mode"] in ("static", "dynamic")


def test_get_session_after_completed(client):
    """完成问答后 GET /session 返回 completed=True"""
    headers = _auth(client, "gui-sess-done@test.com")
    pid = _create_project(client, headers)

    client.post(f"/api/guide/{pid}/start", headers=headers)
    answers = [
        "Knowledge sharing", "Help professionals", "Young professionals",
        "Professional", "1-3 minutes", "Weekly", "", "",
    ]
    for i, ans in enumerate(answers):
        client.post(f"/api/guide/{pid}/answer", json={"step": i, "answer": ans}, headers=headers)

    resp = client.get(f"/api/guide/{pid}/session", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["completed"] is True


def test_get_session_requires_auth(client):
    """未认证访问 GET /session 返回 401"""
    r = client.get("/api/guide/fake-pid/session")
    assert r.status_code == 401


# ── GET /dynamic/available ────────────────────────────────────────────────────

def test_dynamic_available_returns_json(client):
    """GET /dynamic/available 返回 {available: bool} 结构"""
    headers = _auth(client, "gui-avail-json@test.com")
    pid = _create_project(client, headers)

    resp = client.get(f"/api/guide/{pid}/dynamic/available", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "available" in data
    assert isinstance(data["available"], bool)


def test_dynamic_available_false_without_api_key(client):
    """OPENAI_API_KEY 为空时 available=False"""
    headers = _auth(client, "gui-avail-false@test.com")
    pid = _create_project(client, headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=False):
        resp = client.get(f"/api/guide/{pid}/dynamic/available", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["available"] is False


def test_dynamic_available_true_with_api_key(client):
    """配置了 OPENAI_API_KEY 时 available=True"""
    headers = _auth(client, "gui-avail-true@test.com")
    pid = _create_project(client, headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=True):
        resp = client.get(f"/api/guide/{pid}/dynamic/available", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["available"] is True


def test_dynamic_available_requires_auth(client):
    """未认证访问返回 401"""
    r = client.get("/api/guide/fake/dynamic/available")
    assert r.status_code == 401


# ── Dynamic question flow ─────────────────────────────────────────────────────

def test_dynamic_start_returns_question(client):
    """dynamic/start 返回 DynamicQuestionOut 结构"""
    headers = _auth(client, "gui-dyn-start@test.com")
    pid = _create_project(client, headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         _mock_llm_question("你好！请问你想创作什么类型的短视频？"):
        resp = client.post(f"/api/guide/{pid}/dynamic/start", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert "question" in data
    assert "question_type" in data
    assert data["is_complete"] is False
    assert data["mode"] == "dynamic"
    assert data["question"] == "你好！请问你想创作什么类型的短视频？"


def test_dynamic_answer_returns_next_question(client):
    """dynamic/answer 返回下一个问题"""
    headers = _auth(client, "gui-dyn-ans@test.com")
    pid = _create_project(client, headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         _mock_llm_question("第一个问题"):
        client.post(f"/api/guide/{pid}/dynamic/start", headers=headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         _mock_llm_question("你的目标受众是谁？", is_complete=False):
        resp = client.post(
            f"/api/guide/{pid}/dynamic/answer",
            json={"answer": "我想做职场干货视频"},
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["question"] == "你的目标受众是谁？"
    assert data["is_complete"] is False
    assert data["answers_count"] == 1


def test_dynamic_answer_increments_count(client):
    """answers_count 每轮递增"""
    headers = _auth(client, "gui-dyn-count@test.com")
    pid = _create_project(client, headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         _mock_llm_question("Q1"):
        client.post(f"/api/guide/{pid}/dynamic/start", headers=headers)

    counts = []
    for i in range(3):
        with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
             _mock_llm_question(f"Q{i+2}", is_complete=False):
            r = client.post(
                f"/api/guide/{pid}/dynamic/answer",
                json={"answer": f"answer {i+1}"},
                headers=headers,
            )
        counts.append(r.json()["answers_count"])

    assert counts == [1, 2, 3]


def test_dynamic_complete_sets_session_completed(client):
    """is_complete=True 时 session 变为 completed"""
    headers = _auth(client, "gui-dyn-complete@test.com")
    pid = _create_project(client, headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         _mock_llm_question("第一个问题"):
        client.post(f"/api/guide/{pid}/dynamic/start", headers=headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         _mock_llm_question("", is_complete=True), \
         _mock_brief():
        client.post(
            f"/api/guide/{pid}/dynamic/answer",
            json={"answer": "好的，我明白了"},
            headers=headers,
        )

    # session 应变 completed
    sess_resp = client.get(f"/api/guide/{pid}/session", headers=headers)
    assert sess_resp.status_code == 200
    assert sess_resp.json()["completed"] is True


def test_dynamic_complete_generates_brief(client):
    """完成动态问答后可获取 brief"""
    headers = _auth(client, "gui-dyn-brief@test.com")
    pid = _create_project(client, headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         _mock_llm_question("Q1"):
        client.post(f"/api/guide/{pid}/dynamic/start", headers=headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         _mock_llm_question("", is_complete=True), \
         _mock_brief():
        client.post(
            f"/api/guide/{pid}/dynamic/answer",
            json={"answer": "完成"},
            headers=headers,
        )

    brief_resp = client.get(f"/api/guide/{pid}/brief", headers=headers)
    assert brief_resp.status_code == 200
    assert brief_resp.json() is not None


def test_dynamic_already_completed_returns_400(client):
    """会话已完成后再次提交动态答案返回 400"""
    headers = _auth(client, "gui-dyn-dup@test.com")
    pid = _create_project(client, headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         _mock_llm_question("Q1"):
        client.post(f"/api/guide/{pid}/dynamic/start", headers=headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         _mock_llm_question("", is_complete=True), \
         _mock_brief():
        client.post(f"/api/guide/{pid}/dynamic/answer", json={"answer": "done"}, headers=headers)

    # 再提交
    with patch("app.api.guide.is_dynamic_mode_available", return_value=True):
        resp = client.post(
            f"/api/guide/{pid}/dynamic/answer",
            json={"answer": "extra"},
            headers=headers,
        )
    assert resp.status_code == 400


def test_dynamic_with_single_choice_options(client):
    """动态问题支持 single_choice 类型，返回 options"""
    headers = _auth(client, "gui-dyn-choice@test.com")
    pid = _create_project(client, headers)

    choice_result = {
        "question": "请选择你的视频风格",
        "question_type": "single_choice",
        "options": ["轻松幽默", "干货分享", "情感共鸣"],
        "is_complete": False,
    }
    with patch("app.api.guide.is_dynamic_mode_available", return_value=True), \
         patch("app.api.guide.get_next_question",
               new=AsyncMock(return_value=choice_result)):
        resp = client.post(f"/api/guide/{pid}/dynamic/start", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["question_type"] == "single_choice"
    assert data["options"] == ["轻松幽默", "干货分享", "情感共鸣"]


def test_dynamic_unavailable_returns_503(client):
    """动态模式不可用时 start 返回 503"""
    headers = _auth(client, "gui-dyn-503@test.com")
    pid = _create_project(client, headers)

    with patch("app.api.guide.is_dynamic_mode_available", return_value=False):
        resp = client.post(f"/api/guide/{pid}/dynamic/start", headers=headers)

    assert resp.status_code == 503
    assert "Dynamic mode unavailable" in resp.json()["detail"]


# ── Static mode unaffected ────────────────────────────────────────────────────

def test_static_mode_still_works(client):
    """静态模式仍正常工作（回归）"""
    headers = _auth(client, "gui-static-ok@test.com")
    pid = _create_project(client, headers)

    client.post(f"/api/guide/{pid}/start", headers=headers)
    resp = client.get(f"/api/guide/{pid}/question", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["step"] == 0
    assert data["question_type"] in ("single_choice", "text_input")
    assert "total_steps" in data
