"""
tests/test_sse_streaming.py — SSE 流式输出测试

覆盖场景：
- GET /generate/{project_id}/stream：逐 token 流式生成剧本
- GET /generate/{project_id}/stream：完整输出后以 [DONE] 结束
- POST /generate/{project_id}/save：保存流式生成的结果到 DB
- POST /{script_id}/rewrite/stream：流式段落改写
- POST /{script_id}/rewrite/stream：改写后 [DONE]
- SSE 格式校验：每行 data: <content>\\n\\n
- 越界 paragraph_index → 400
- LLM 错误 → event: error
- 跨用户隔离
"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from typing import AsyncIterator

# ── 固定测试数据 ───────────────────────────────────────────────────────────────

SCRIPT_CONTENT = {
    "title": "5个职场效率神器",
    "hook": "你有没有感觉一天工作下来什么都没做完？",
    "sections": [
        {
            "id": 1,
            "title": "引入问题",
            "content": "很多职场新人都有这个困惑：明明很忙，但到了下班时间发现重要的事情一件都没做完。",
            "duration_estimate": "15 seconds",
        },
        {
            "id": 2,
            "title": "核心方法",
            "content": "今天分享5个我用了3年的效率工具，帮你把工作时间缩短30%。",
            "duration_estimate": "20 seconds",
        },
    ],
    "cta": "关注我，每周分享一个职场干货。",
    "total_duration_estimate": "60 seconds",
    "notes": "",
}

SCRIPT_JSON_STR = json.dumps(SCRIPT_CONTENT, ensure_ascii=False)


# ── Async generator mock helpers ──────────────────────────────────────────────

async def make_token_stream(*tokens: str) -> AsyncIterator[str]:
    """Create an async generator that yields tokens one by one."""
    for t in tokens:
        yield t


def patch_generate_stream(tokens):
    """Patch generate_script_stream to yield given tokens."""
    async def _gen(*args, **kwargs):
        for t in tokens:
            yield t
    return patch("app.services.script_service.generate_script_stream", side_effect=_gen)


def patch_rewrite_stream(tokens):
    """Patch rewrite_paragraph_stream to yield given tokens."""
    async def _gen(*args, **kwargs):
        for t in tokens:
            yield t
    return patch("app.services.script_service.rewrite_paragraph_stream", side_effect=_gen)


# ── E2E Helpers ────────────────────────────────────────────────────────────────

def _register(client, email, password="pw123456"):
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(client, email, password="pw123456"):
    tok = _register(client, email, password)
    return {"Authorization": f"Bearer {tok}"}


def _create_project(client, headers):
    r = client.post("/api/projects", json={"name": "SSE Test", "description": "test"}, headers=headers)
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


def _generate_script_nonstream(client, headers, pid):
    """生成非流式剧本，用于获取 script_id"""
    with patch("app.services.script_service.client") as mock_client:
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = SCRIPT_JSON_STR
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
        r = client.post(f"/api/scripts/generate/{pid}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _parse_sse(response_text: str) -> list[str]:
    """
    解析 SSE 文本，返回所有 data 字段的值列表（不含 [DONE]）。
    格式: "data: <value>\\n\\n"
    """
    tokens = []
    for line in response_text.splitlines():
        line = line.strip()
        if line.startswith("data: ") and line != "data: [DONE]":
            tokens.append(line[len("data: "):])
    return tokens


def _has_done(response_text: str) -> bool:
    return "data: [DONE]" in response_text


def _has_error_event(response_text: str) -> bool:
    return "event: error" in response_text


# ── SSE 格式测试 ──────────────────────────────────────────────────────────────

def test_generate_stream_sse_format(client):
    """生成剧本 SSE 流的格式正确：每行 data: <x>，最后 [DONE]"""
    headers = _auth(client, "sse-fmt@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    tokens = ["{\"title\":", " \"测试\"", "}"]
    async def _gen(brief):
        for t in tokens:
            yield t

    with patch("app.api.scripts.generate_script_stream", side_effect=_gen):
        resp = client.post(
            f"/api/scripts/generate/{pid}/stream",
            headers=headers,
        )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    text = resp.text

    # 每个 token 都要出现在 SSE data 行中
    for token in tokens:
        assert token in text

    assert _has_done(text)


def test_generate_stream_tokens_in_order(client):
    """流式生成的 token 顺序正确"""
    headers = _auth(client, "sse-order@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    tokens = ["part1", "part2", "part3"]

    async def _gen(brief):
        for t in tokens:
            yield t

    with patch("app.api.scripts.generate_script_stream", side_effect=_gen):
        resp = client.post(f"/api/scripts/generate/{pid}/stream", headers=headers)

    assert resp.status_code == 200
    body = resp.text
    pos = [body.index(t) for t in tokens]
    assert pos == sorted(pos), "Tokens should appear in order"


def test_generate_stream_ends_with_done(client):
    """SSE 流最后一个事件是 [DONE]"""
    headers = _auth(client, "sse-done@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    async def _gen(brief):
        yield SCRIPT_JSON_STR

    with patch("app.api.scripts.generate_script_stream", side_effect=_gen):
        resp = client.post(f"/api/scripts/generate/{pid}/stream", headers=headers)

    assert _has_done(resp.text)
    # [DONE] 应该是最后一个 data 行
    lines = [l.strip() for l in resp.text.splitlines() if l.strip().startswith("data:")]
    assert lines[-1] == "data: [DONE]"


def test_generate_stream_llm_error_sends_error_event(client):
    """LLM 报错时 SSE 发送 event: error"""
    headers = _auth(client, "sse-err@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    async def _gen_err(brief):
        raise RuntimeError("OpenAI timeout")
        yield  # make it an async generator

    with patch("app.api.scripts.generate_script_stream", side_effect=_gen_err):
        resp = client.post(f"/api/scripts/generate/{pid}/stream", headers=headers)

    assert resp.status_code == 200  # SSE 已开始，不能改 HTTP status
    assert _has_error_event(resp.text)


def test_generate_stream_requires_guide_complete(client):
    """引导未完成时返回 4xx 错误"""
    headers = _auth(client, "sse-noguide@test.com")
    pid = _create_project(client, headers)
    # 不完成引导（guide session 不存在 → 404；存在但未完成 → 400）

    resp = client.post(f"/api/scripts/generate/{pid}/stream", headers=headers)
    assert resp.status_code in (400, 404)


def test_generate_stream_requires_auth(client):
    """未认证返回 401"""
    resp = client.post("/api/scripts/generate/nonexistent/stream")
    assert resp.status_code == 401


# ── Save streamed script ───────────────────────────────────────────────────────

def test_save_streamed_script(client):
    """前端拼接完毕后 save 到 DB，返回完整 ScriptOut"""
    headers = _auth(client, "sse-save@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    resp = client.post(
        f"/api/scripts/generate/{pid}/save",
        json={"content": SCRIPT_CONTENT},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"]["title"] == SCRIPT_CONTENT["title"]
    assert data["version"] == 1
    assert data["is_latest"] is True


def test_save_increments_version(client):
    """多次 save 版本递增"""
    headers = _auth(client, "sse-ver@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    # first save
    r1 = client.post(
        f"/api/scripts/generate/{pid}/save",
        json={"content": SCRIPT_CONTENT},
        headers=headers,
    )
    assert r1.status_code == 200
    assert r1.json()["version"] == 1

    # second save (re-generate)
    r2 = client.post(
        f"/api/scripts/generate/{pid}/save",
        json={"content": {**SCRIPT_CONTENT, "title": "v2 title"}},
        headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json()["version"] == 2
    assert r2.json()["is_latest"] is True

    # first is no longer latest
    scripts = client.get(f"/api/scripts/{pid}", headers=headers).json()
    assert sum(1 for s in scripts if s["is_latest"]) == 1


def test_save_invalid_content_returns_400(client):
    """content 不是 dict 时返回 400"""
    headers = _auth(client, "sse-bad@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)

    resp = client.post(
        f"/api/scripts/generate/{pid}/save",
        json={"content": "not a dict"},
        headers=headers,
    )
    assert resp.status_code == 400


# ── SSE 段落改写流 ─────────────────────────────────────────────────────────────

def test_rewrite_stream_format(client):
    """段落改写 SSE 格式正确"""
    headers = _auth(client, "rw-stream-fmt@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)
    script_id = _generate_script_nonstream(client, headers, pid)

    tokens = ["改写", "后的", "内容"]

    async def _gen(content, idx, instruction):
        for t in tokens:
            yield t

    with patch("app.api.scripts.rewrite_paragraph_stream", side_effect=_gen):
        resp = client.post(
            f"/api/scripts/{script_id}/rewrite/stream",
            json={"paragraph_index": 0, "instruction": "更幽默", "preview": True},
            headers=headers,
        )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert _has_done(resp.text)

    parsed = _parse_sse(resp.text)
    combined = "".join(parsed)
    assert "改写" in combined
    assert "后的" in combined


def test_rewrite_stream_tokens_concatenate(client):
    """将 SSE token 拼接后等于完整改写文本"""
    headers = _auth(client, "rw-stream-cat@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)
    script_id = _generate_script_nonstream(client, headers, pid)

    expected = "今天分享一个超实用的方法，保证让你效率翻倍！"
    tokens = list(expected)  # char by char

    async def _gen(content, idx, instruction):
        for t in tokens:
            yield t

    with patch("app.api.scripts.rewrite_paragraph_stream", side_effect=_gen):
        resp = client.post(
            f"/api/scripts/{script_id}/rewrite/stream",
            json={"paragraph_index": 1, "instruction": "更吸引人", "preview": True},
            headers=headers,
        )

    parsed = _parse_sse(resp.text)
    # 还原 escape 的换行符
    combined = "".join(t.replace("\\n", "\n") for t in parsed)
    assert combined == expected


def test_rewrite_stream_out_of_range_returns_400(client):
    """越界 paragraph_index 在 HTTP 层就返回 400（不进入 SSE 流）"""
    headers = _auth(client, "rw-stream-oob@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)
    script_id = _generate_script_nonstream(client, headers, pid)

    resp = client.post(
        f"/api/scripts/{script_id}/rewrite/stream",
        json={"paragraph_index": 99, "instruction": "test", "preview": True},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "out of range" in resp.json()["detail"]


def test_rewrite_stream_llm_error_sends_error_event(client):
    """LLM 异步生成报错 → SSE event: error"""
    headers = _auth(client, "rw-stream-err@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)
    script_id = _generate_script_nonstream(client, headers, pid)

    async def _gen_err(content, idx, instruction):
        raise RuntimeError("Connection timeout")
        yield

    with patch("app.api.scripts.rewrite_paragraph_stream", side_effect=_gen_err):
        resp = client.post(
            f"/api/scripts/{script_id}/rewrite/stream",
            json={"paragraph_index": 0, "instruction": "更幽默", "preview": True},
            headers=headers,
        )

    assert resp.status_code == 200
    assert _has_error_event(resp.text)


def test_rewrite_stream_cross_user_isolation(client):
    """其他用户不能改写别人的剧本（流式端点同样鉴权）"""
    headers_a = _auth(client, "rw-stream-a@test.com")
    headers_b = _auth(client, "rw-stream-b@test.com")

    pid = _create_project(client, headers_a)
    _complete_guide(client, headers_a, pid)
    script_id = _generate_script_nonstream(client, headers_a, pid)

    resp = client.post(
        f"/api/scripts/{script_id}/rewrite/stream",
        json={"paragraph_index": 0, "instruction": "test", "preview": True},
        headers=headers_b,
    )
    assert resp.status_code == 404


def test_rewrite_stream_requires_auth(client):
    """未认证返回 401"""
    resp = client.post(
        "/api/scripts/nonexistent/rewrite/stream",
        json={"paragraph_index": 0, "instruction": "test", "preview": True},
    )
    assert resp.status_code == 401


# ── Service unit tests: async generator behavior ──────────────────────────────

async def test_generate_script_stream_yields_tokens():
    """generate_script_stream 正确 yield LLM chunks"""
    from app.services.script_service import generate_script_stream

    async def fake_stream():
        chunks = ["{", "\"title\"", ": \"test\"", "}"]
        for c in chunks:
            delta = MagicMock()
            delta.content = c
            choice = MagicMock()
            choice.delta = delta
            chunk = MagicMock()
            chunk.choices = [choice]
            yield chunk

    with patch("app.services.script_service.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=fake_stream())
        tokens = []
        async for token in generate_script_stream({"topic": "test"}):
            tokens.append(token)

    assert tokens == ["{", "\"title\"", ": \"test\"", "}"]
    assert "".join(tokens) == "{\"title\": \"test\"}"


async def test_rewrite_paragraph_stream_yields_tokens():
    """rewrite_paragraph_stream 正确 yield 改写 chunks"""
    from app.services.script_service import rewrite_paragraph_stream

    expected_tokens = ["改", "写", "后", "内", "容"]

    async def fake_stream():
        for c in expected_tokens:
            delta = MagicMock()
            delta.content = c
            choice = MagicMock()
            choice.delta = delta
            chunk = MagicMock()
            chunk.choices = [choice]
            yield chunk

    with patch("app.services.script_service.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=fake_stream())
        tokens = []
        async for token in rewrite_paragraph_stream(SCRIPT_CONTENT, 0, "更幽默"):
            tokens.append(token)

    assert tokens == expected_tokens


async def test_rewrite_paragraph_stream_out_of_range():
    """越界索引抛出 ValueError（流启动前）"""
    from app.services.script_service import rewrite_paragraph_stream

    with pytest.raises(ValueError, match="out of range"):
        async for _ in rewrite_paragraph_stream(SCRIPT_CONTENT, 99, "test"):
            pass


async def test_generate_script_stream_skips_none_content():
    """content 为 None 的 chunk 被跳过（不 yield 空字符串）"""
    from app.services.script_service import generate_script_stream

    async def fake_stream_with_none():
        for c in ["abc", None, "def"]:
            delta = MagicMock()
            delta.content = c
            choice = MagicMock()
            choice.delta = delta
            chunk = MagicMock()
            chunk.choices = [choice]
            yield chunk

    with patch("app.services.script_service.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=fake_stream_with_none())
        tokens = []
        async for token in generate_script_stream({}):
            tokens.append(token)

    assert tokens == ["abc", "def"]
    assert None not in tokens
