"""
tests/test_script_format.py — 剧本格式支持测试

覆盖场景：
- voiceover 格式（默认）生成 → format 字段为 voiceover
- storyboard 格式生成 → format 字段为 storyboard，sections 含 shot_type/visual/voiceover
- SSE 流式生成支持 format 参数
- save 端点支持 format 字段
- format 字段存 DB，通过 GET 可查询
- 不合法 format 值自动降级到 voiceover
- format 字段在 ScriptOut 中正确返回
- 服务层 generate_script(brief, fmt='storyboard') 走 STORYBOARD_SYSTEM_PROMPT
- 服务层 generate_script_stream(brief, fmt='storyboard') 走 storyboard system prompt
"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# ── 测试数据 ──────────────────────────────────────────────────────────────────

VOICEOVER_CONTENT = {
    "title": "3个早起习惯改变你的人生",
    "hook": "你有没有发现，那些成功的人几乎都是早起的？",
    "sections": [
        {
            "id": 1,
            "title": "引入问题",
            "content": "很多人晚上睡不好，早上爬不起来，一天都没精神。",
            "duration_estimate": "10 seconds",
        },
        {
            "id": 2,
            "title": "核心方法",
            "content": "今天告诉你3个早起习惯，让你每天多出2小时。",
            "duration_estimate": "15 seconds",
        },
    ],
    "cta": "关注我，每天分享一个生活干货。",
    "total_duration_estimate": "60 seconds",
    "notes": "",
}

STORYBOARD_CONTENT = {
    "title": "3个早起习惯改变你的人生",
    "hook": "特写镜头：闹钟6点，窗外朝阳升起",
    "sections": [
        {
            "id": 1,
            "title": "引入问题",
            "shot_type": "近景",
            "visual": "主播坐在书桌前，背景整洁书架",
            "voiceover": "很多人晚上睡不好，早上爬不起来，一天都没精神。",
            "caption": "你也有这个问题吗？",
            "duration_estimate": "10 seconds",
        },
        {
            "id": 2,
            "title": "核心方法",
            "shot_type": "信息图",
            "visual": "动态文字：早起3步骤",
            "voiceover": "今天告诉你3个早起习惯，让你每天多出2小时。",
            "caption": "方法一：固定起床时间",
            "duration_estimate": "15 seconds",
        },
    ],
    "cta": "关注我，每天分享一个生活干货。",
    "total_duration_estimate": "60 seconds",
    "notes": "注意光线充足",
}


# ── E2E Helpers ───────────────────────────────────────────────────────────────

def _auth(client, email, password="pw123456"):
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _create_project(client, headers):
    r = client.post("/api/projects", json={"name": "Format Test", "description": ""}, headers=headers)
    assert r.status_code == 200
    return r.json()["id"]


def _complete_guide(client, headers, pid):
    client.post(f"/api/guide/{pid}/start", headers=headers)
    answers = [
        "Knowledge sharing", "Help professionals", "Young professionals",
        "Professional", "1-3 minutes", "Weekly", "", "",
    ]
    for i, ans in enumerate(answers):
        r = client.post(f"/api/guide/{pid}/answer", json={"step": i, "answer": ans}, headers=headers)
        assert r.status_code == 200


def _mock_llm(content_dict):
    """返回 mock LLM 同步调用 patch context"""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps(content_dict, ensure_ascii=False)
    return patch("app.services.script_service.client") if False else \
        patch("app.services.script_service.client",
              **{"chat.completions.create": AsyncMock(return_value=mock_resp)})


def _mock_llm_ctx(content_dict):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps(content_dict, ensure_ascii=False)
    m = MagicMock()
    m.chat.completions.create = AsyncMock(return_value=mock_resp)
    return patch("app.services.script_service.client", m)


# ── format=voiceover（默认）────────────────────────────────────────────────────

def test_generate_voiceover_default_format(client):
    """不传 format，默认生成 voiceover 格式"""
    headers = _auth(client, "fmt-vo-default@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    with _mock_llm_ctx(VOICEOVER_CONTENT):
        resp = client.post(f"/api/scripts/generate/{pid}", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "voiceover"
    assert data["content"]["title"] == VOICEOVER_CONTENT["title"]


def test_generate_voiceover_explicit_format(client):
    """显式传 format=voiceover"""
    headers = _auth(client, "fmt-vo-explicit@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    with _mock_llm_ctx(VOICEOVER_CONTENT):
        resp = client.post(
            f"/api/scripts/generate/{pid}",
            json={"format": "voiceover"},
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["format"] == "voiceover"


# ── format=storyboard ─────────────────────────────────────────────────────────

def test_generate_storyboard_format(client):
    """传 format=storyboard，生成分镜格式剧本"""
    headers = _auth(client, "fmt-sb@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    with _mock_llm_ctx(STORYBOARD_CONTENT):
        resp = client.post(
            f"/api/scripts/generate/{pid}",
            json={"format": "storyboard"},
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "storyboard"
    # storyboard sections 含 shot_type/visual/voiceover
    section = data["content"]["sections"][0]
    assert "shot_type" in section
    assert "visual" in section
    assert "voiceover" in section


def test_storyboard_uses_different_system_prompt(client):
    """storyboard 格式调用时，传给 LLM 的 system prompt 应是 STORYBOARD_SYSTEM_PROMPT"""
    headers = _auth(client, "fmt-sb-prompt@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps(STORYBOARD_CONTENT, ensure_ascii=False)
    mock_create = AsyncMock(return_value=mock_resp)

    with patch("app.services.script_service.client") as mock_client:
        mock_client.chat.completions.create = mock_create
        resp = client.post(
            f"/api/scripts/generate/{pid}",
            json={"format": "storyboard"},
            headers=headers,
        )

    assert resp.status_code == 200
    call_args = mock_create.call_args
    # kwargs or positional args[0]
    messages = (
        call_args.kwargs.get("messages")
        or (call_args.args[0] if call_args.args else None)
        or []
    )
    if not messages:
        # try all kwargs
        all_kwargs = call_args.kwargs
        for v in all_kwargs.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and "role" in v[0]:
                messages = v
                break
    system_msgs = [m for m in messages if m.get("role") == "system"]
    assert system_msgs, f"No system message found. call_args={call_args}"
    system_content = system_msgs[0]["content"]
    assert "shot_type" in system_content or "storyboard" in system_content.lower()


def test_voiceover_uses_voiceover_system_prompt(client):
    """voiceover 格式调用时，system prompt 不含 storyboard 字段"""
    headers = _auth(client, "fmt-vo-prompt@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps(VOICEOVER_CONTENT, ensure_ascii=False)
    mock_create = AsyncMock(return_value=mock_resp)

    with patch("app.services.script_service.client") as mock_client:
        mock_client.chat.completions.create = mock_create
        resp = client.post(
            f"/api/scripts/generate/{pid}",
            json={"format": "voiceover"},
            headers=headers,
        )

    assert resp.status_code == 200
    call_args = mock_create.call_args
    messages = call_args.kwargs.get("messages") or []
    system_msgs = [m for m in messages if m.get("role") == "system"]
    assert system_msgs
    # voiceover prompt 不含 storyboard 特有字段
    assert "shot_type" not in system_msgs[0]["content"]


# ── format 字段持久化 ─────────────────────────────────────────────────────────

def test_format_persisted_in_db(client):
    """format 字段正确存储，GET 接口返回"""
    headers = _auth(client, "fmt-persist@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    with _mock_llm_ctx(STORYBOARD_CONTENT):
        r = client.post(
            f"/api/scripts/generate/{pid}",
            json={"format": "storyboard"},
            headers=headers,
        )
    script_id = r.json()["id"]

    # 通过列表接口查询
    scripts = client.get(f"/api/scripts/{pid}", headers=headers).json()
    assert isinstance(scripts, list)
    found = next((s for s in scripts if s["id"] == script_id), None)
    assert found is not None
    assert found["format"] == "storyboard"


def test_format_in_latest_endpoint(client):
    """GET /latest 返回的 format 字段正确"""
    headers = _auth(client, "fmt-latest@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    with _mock_llm_ctx(STORYBOARD_CONTENT):
        client.post(
            f"/api/scripts/generate/{pid}",
            json={"format": "storyboard"},
            headers=headers,
        )

    latest = client.get(f"/api/scripts/{pid}/latest", headers=headers).json()
    assert latest["format"] == "storyboard"


# ── invalid format 降级 ───────────────────────────────────────────────────────

def test_invalid_format_returns_422(client):
    """不合法的 format 值返回 422（pydantic 校验失败）"""
    headers = _auth(client, "fmt-invalid@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    resp = client.post(
        f"/api/scripts/generate/{pid}",
        json={"format": "anime"},
        headers=headers,
    )
    assert resp.status_code == 422


# ── SSE stream 支持 format ────────────────────────────────────────────────────

def test_sse_stream_voiceover_format(client):
    """SSE stream 端点默认生成 voiceover（不传 format）"""
    headers = _auth(client, "fmt-sse-vo@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    async def _gen(brief, fmt="voiceover"):
        assert fmt == "voiceover"
        yield json.dumps(VOICEOVER_CONTENT)

    with patch("app.api.scripts.generate_script_stream", side_effect=_gen):
        resp = client.post(f"/api/scripts/generate/{pid}/stream", headers=headers)

    assert resp.status_code == 200
    assert "data: [DONE]" in resp.text


def test_sse_stream_storyboard_format(client):
    """SSE stream 端点传 format=storyboard，正确转发给服务层"""
    headers = _auth(client, "fmt-sse-sb@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    received_fmt = []

    async def _gen(brief, fmt="voiceover"):
        received_fmt.append(fmt)
        yield json.dumps(STORYBOARD_CONTENT)

    with patch("app.api.scripts.generate_script_stream", side_effect=_gen):
        resp = client.post(
            f"/api/scripts/generate/{pid}/stream",
            json={"format": "storyboard"},
            headers=headers,
        )

    assert resp.status_code == 200
    assert received_fmt == ["storyboard"]
    assert "data: [DONE]" in resp.text


# ── save 端点支持 format ──────────────────────────────────────────────────────

def test_save_storyboard_format(client):
    """save 端点接受 format=storyboard，存到 DB"""
    headers = _auth(client, "fmt-save-sb@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    resp = client.post(
        f"/api/scripts/generate/{pid}/save",
        json={"content": STORYBOARD_CONTENT, "format": "storyboard"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["format"] == "storyboard"


def test_save_defaults_to_voiceover(client):
    """save 端点不传 format，默认 voiceover"""
    headers = _auth(client, "fmt-save-default@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    resp = client.post(
        f"/api/scripts/generate/{pid}/save",
        json={"content": VOICEOVER_CONTENT},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["format"] == "voiceover"


def test_save_invalid_format_falls_back_to_voiceover(client):
    """save 端点不合法 format 降级到 voiceover（不崩溃）"""
    headers = _auth(client, "fmt-save-bad@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    resp = client.post(
        f"/api/scripts/generate/{pid}/save",
        json={"content": VOICEOVER_CONTENT, "format": "unknown_type"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["format"] == "voiceover"


# ── Service 单元测试 ──────────────────────────────────────────────────────────

async def test_service_generate_script_voiceover():
    """generate_script(brief, fmt='voiceover') 走 SYSTEM_PROMPT"""
    from app.services.script_service import generate_script, SYSTEM_PROMPT

    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps(VOICEOVER_CONTENT)
    mock_create = AsyncMock(return_value=mock_resp)

    with patch("app.services.script_service.client") as mock_client:
        mock_client.chat.completions.create = mock_create
        result = await generate_script({"topic_category": "test"}, fmt="voiceover")

    assert result["title"] == VOICEOVER_CONTENT["title"]
    call_kwargs = mock_create.call_args.kwargs
    msgs = call_kwargs.get("messages", [])
    assert any(m.get("content") == SYSTEM_PROMPT for m in msgs if m.get("role") == "system")


async def test_service_generate_script_storyboard():
    """generate_script(brief, fmt='storyboard') 走 STORYBOARD_SYSTEM_PROMPT"""
    from app.services.script_service import generate_script, STORYBOARD_SYSTEM_PROMPT

    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps(STORYBOARD_CONTENT)
    mock_create = AsyncMock(return_value=mock_resp)

    with patch("app.services.script_service.client") as mock_client:
        mock_client.chat.completions.create = mock_create
        result = await generate_script({"topic_category": "test"}, fmt="storyboard")

    assert result["title"] == STORYBOARD_CONTENT["title"]
    call_kwargs = mock_create.call_args.kwargs
    msgs = call_kwargs.get("messages", [])
    assert any(m.get("content") == STORYBOARD_SYSTEM_PROMPT for m in msgs if m.get("role") == "system")


async def test_service_generate_script_stream_storyboard():
    """generate_script_stream(brief, fmt='storyboard') 走 storyboard system prompt"""
    from app.services.script_service import generate_script_stream, STORYBOARD_SYSTEM_PROMPT

    tokens = ["{", '"title"', ': "test"', "}"]

    async def fake_stream():
        for t in tokens:
            delta = MagicMock(); delta.content = t
            choice = MagicMock(); choice.delta = delta
            chunk = MagicMock(); chunk.choices = [choice]
            yield chunk

    mock_create = AsyncMock(return_value=fake_stream())

    with patch("app.services.script_service.client") as mock_client:
        mock_client.chat.completions.create = mock_create
        result_tokens = []
        async for tok in generate_script_stream({"topic_category": "test"}, fmt="storyboard"):
            result_tokens.append(tok)

    assert result_tokens == tokens
    call_kwargs = mock_create.call_args.kwargs
    msgs = call_kwargs.get("messages", [])
    assert any(m.get("content") == STORYBOARD_SYSTEM_PROMPT for m in msgs if m.get("role") == "system")


async def test_service_brief_prompt_includes_tone():
    """Brief 生成时包含 tone 字段（Brief schema 扩展）"""
    from app.services.script_service import _build_brief_prompt

    brief = {"topic_category": "健康", "tone": "轻松幽默"}
    prompt = _build_brief_prompt(brief)
    assert "轻松幽默" in prompt
    assert "Tone:" in prompt


async def test_service_generate_script_stream_voiceover_default():
    """generate_script_stream 默认 fmt='voiceover' 走 SYSTEM_PROMPT"""
    from app.services.script_service import generate_script_stream, SYSTEM_PROMPT

    async def fake_stream():
        delta = MagicMock(); delta.content = "{}"
        choice = MagicMock(); choice.delta = delta
        chunk = MagicMock(); chunk.choices = [choice]
        yield chunk

    mock_create = AsyncMock(return_value=fake_stream())

    with patch("app.services.script_service.client") as mock_client:
        mock_client.chat.completions.create = mock_create
        async for _ in generate_script_stream({}):
            pass

    msgs = mock_create.call_args.kwargs.get("messages", [])
    assert any(m.get("content") == SYSTEM_PROMPT for m in msgs if m.get("role") == "system")
