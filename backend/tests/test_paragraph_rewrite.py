"""
tests/test_paragraph_rewrite.py — 段落重写 API 测试

覆盖场景：
- POST /{script_id}/rewrite  preview=true  → 返回改写结果，不写 DB
- POST /{script_id}/rewrite  preview=false → 直接写入 DB
- POST /{script_id}/rewrite/apply          → 应用预览文本到 DB
- 越界 paragraph_index → 400
- LLM 报错 → 502
- 跨用户隔离 → 404
- apply_rewrite 工具函数正确性
- rewrite_paragraph 服务层 mock 测试
"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

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
        {
            "id": 3,
            "title": "总结",
            "content": "试试这些方法，你会发现工作其实可以更轻松。",
            "duration_estimate": "10 seconds",
        },
    ],
    "cta": "关注我，每周分享一个职场干货。",
    "total_duration_estimate": "60 seconds",
}

REWRITTEN_TEXT = "你是不是也经历过：加班到很晚，结果项目deadline一个都没按时交？这个问题太真实了！"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _register(client, email, password="pw123456"):
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(client, email, password="pw123456"):
    tok = _register(client, email, password)
    return {"Authorization": f"Bearer {tok}"}


def _create_project(client, headers):
    r = client.post("/api/projects", json={"name": "Rewrite Test", "description": "test"}, headers=headers)
    assert r.status_code == 200
    return r.json()["id"]


def _complete_guide(client, headers, pid):
    """静态模式完成 8 步引导问答"""
    client.post(f"/api/guide/{pid}/start", headers=headers)
    answers = [
        "Knowledge sharing", "Help professionals", "Young professionals",
        "Professional", "1-3 minutes", "Weekly", "", "",
    ]
    for i, ans in enumerate(answers):
        r = client.post(f"/api/guide/{pid}/answer", json={"step": i, "answer": ans}, headers=headers)
        assert r.status_code == 200


def _generate_script(client, headers, pid):
    """Mock LLM 生成剧本"""
    with patch("app.services.script_service.client") as mock_client:
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = json.dumps(SCRIPT_CONTENT)
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
        r = client.post(f"/api/scripts/generate/{pid}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def make_llm_resp(text: str) -> MagicMock:
    resp = MagicMock()
    resp.choices[0].message.content = text
    return resp


# ── E2E Tests: preview mode ────────────────────────────────────────────────────

def test_rewrite_preview_returns_result_without_saving(client):
    """preview=true 时返回改写结果，DB 中原文不变"""
    headers = _auth(client, "rw-preview@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)
    script_id = _generate_script(client, headers, pid)

    with patch("app.services.script_service.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            return_value=make_llm_resp(REWRITTEN_TEXT)
        )
        resp = client.post(
            f"/api/scripts/{script_id}/rewrite",
            json={"paragraph_index": 0, "instruction": "更幽默", "preview": True},
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["rewritten"] == REWRITTEN_TEXT
    assert data["original"] == SCRIPT_CONTENT["sections"][0]["content"]
    assert data["section_title"] == "引入问题"
    assert data["paragraph_index"] == 0
    assert data["instruction"] == "更幽默"
    assert data["applied"] is False

    # 验证 DB 未被修改
    get_resp = client.get(f"/api/scripts/{pid}/latest", headers=headers)
    original_in_db = get_resp.json()["content"]["sections"][0]["content"]
    assert original_in_db == SCRIPT_CONTENT["sections"][0]["content"]


def test_rewrite_direct_apply(client):
    """preview=false 时直接写入 DB"""
    headers = _auth(client, "rw-direct@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)
    script_id = _generate_script(client, headers, pid)

    with patch("app.services.script_service.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            return_value=make_llm_resp(REWRITTEN_TEXT)
        )
        resp = client.post(
            f"/api/scripts/{script_id}/rewrite",
            json={"paragraph_index": 1, "instruction": "更简短", "preview": False},
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["applied"] is True

    # 验证 DB 已更新
    get_resp = client.get(f"/api/scripts/{pid}/latest", headers=headers)
    updated = get_resp.json()["content"]["sections"][1]["content"]
    assert updated == REWRITTEN_TEXT


def test_rewrite_second_and_third_paragraph(client):
    """支持改写任意段落（不只是 index=0）"""
    headers = _auth(client, "rw-any@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)
    script_id = _generate_script(client, headers, pid)

    with patch("app.services.script_service.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            return_value=make_llm_resp("全新的总结段落，号召观众行动起来！")
        )
        resp = client.post(
            f"/api/scripts/{script_id}/rewrite",
            json={"paragraph_index": 2, "instruction": "更有感召力", "preview": False},
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["section_title"] == "总结"


# ── E2E Tests: apply endpoint ──────────────────────────────────────────────────

def test_apply_rewrite_saves_to_db(client):
    """POST /rewrite/apply 将预览文本写入 DB"""
    headers = _auth(client, "rw-apply@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)
    script_id = _generate_script(client, headers, pid)

    resp = client.post(
        f"/api/scripts/{script_id}/rewrite/apply",
        json={"paragraph_index": 0, "rewritten_text": "全新段落文本"},
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["content"]["sections"][0]["content"] == "全新段落文本"
    # 其他段落不受影响
    assert data["content"]["sections"][1]["content"] == SCRIPT_CONTENT["sections"][1]["content"]


def test_apply_rewrite_returns_updated_script(client):
    """apply 返回完整的 ScriptOut"""
    headers = _auth(client, "rw-apply2@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)
    script_id = _generate_script(client, headers, pid)

    resp = client.post(
        f"/api/scripts/{script_id}/rewrite/apply",
        json={"paragraph_index": 1, "rewritten_text": "改写后的核心方法段落"},
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "version" in data
    assert data["content"]["sections"][1]["content"] == "改写后的核心方法段落"


# ── E2E Tests: error cases ─────────────────────────────────────────────────────

def test_rewrite_out_of_range_index_returns_400(client):
    """段落索引越界返回 400"""
    headers = _auth(client, "rw-oob@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)
    script_id = _generate_script(client, headers, pid)

    resp = client.post(
        f"/api/scripts/{script_id}/rewrite",
        json={"paragraph_index": 99, "instruction": "test", "preview": True},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "out of range" in resp.json()["detail"]


def test_apply_out_of_range_index_returns_400(client):
    """apply 端点越界也返回 400"""
    headers = _auth(client, "rw-apply-oob@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)
    script_id = _generate_script(client, headers, pid)

    resp = client.post(
        f"/api/scripts/{script_id}/rewrite/apply",
        json={"paragraph_index": 50, "rewritten_text": "x"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_rewrite_llm_error_returns_502(client):
    """LLM 调用失败返回 502"""
    headers = _auth(client, "rw-llmerr@test.com")
    pid = _create_project(client, headers)
    _complete_guide(client, headers, pid)
    script_id = _generate_script(client, headers, pid)

    with patch("app.services.script_service.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("Connection timeout")
        )
        resp = client.post(
            f"/api/scripts/{script_id}/rewrite",
            json={"paragraph_index": 0, "instruction": "更幽默", "preview": True},
            headers=headers,
        )

    assert resp.status_code == 502
    assert "LLM error" in resp.json()["detail"]


def test_rewrite_cross_user_isolation(client):
    """其他用户不能改写别人的剧本"""
    headers_a = _auth(client, "rw-user-a@test.com")
    headers_b = _auth(client, "rw-user-b@test.com")

    pid = _create_project(client, headers_a)
    _complete_guide(client, headers_a, pid)
    script_id = _generate_script(client, headers_a, pid)

    # user_b 尝试改写 user_a 的剧本
    resp = client.post(
        f"/api/scripts/{script_id}/rewrite",
        json={"paragraph_index": 0, "instruction": "更幽默", "preview": True},
        headers=headers_b,
    )
    assert resp.status_code == 404


def test_rewrite_requires_auth(client):
    """未认证用户返回 401"""
    resp = client.post(
        "/api/scripts/nonexistent/rewrite",
        json={"paragraph_index": 0, "instruction": "test", "preview": True},
    )
    assert resp.status_code == 401


# ── Service unit tests ─────────────────────────────────────────────────────────

async def test_rewrite_paragraph_calls_llm_with_context():
    """rewrite_paragraph 将段落标题、原文、指令全部传入 LLM"""
    from app.services.script_service import rewrite_paragraph

    with patch("app.services.script_service.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            return_value=make_llm_resp(REWRITTEN_TEXT)
        )
        result = await rewrite_paragraph(
            script_content=SCRIPT_CONTENT,
            paragraph_index=0,
            instruction="更幽默",
        )

    assert result["original"] == SCRIPT_CONTENT["sections"][0]["content"]
    assert result["rewritten"] == REWRITTEN_TEXT
    assert result["section_title"] == "引入问题"
    assert result["instruction"] == "更幽默"
    assert result["paragraph_index"] == 0

    # 验证 LLM 被调用时包含必要上下文
    call_args = mock_client.chat.completions.create.call_args
    user_msg = next(m for m in call_args.kwargs["messages"] if m["role"] == "user")
    assert "引入问题" in user_msg["content"]
    assert "更幽默" in user_msg["content"]
    assert SCRIPT_CONTENT["sections"][0]["content"] in user_msg["content"]


async def test_rewrite_paragraph_out_of_range_raises():
    """越界索引抛出 ValueError"""
    from app.services.script_service import rewrite_paragraph

    with pytest.raises(ValueError, match="out of range"):
        await rewrite_paragraph(SCRIPT_CONTENT, paragraph_index=99, instruction="test")


async def test_rewrite_paragraph_negative_index_raises():
    """负数索引抛出 ValueError"""
    from app.services.script_service import rewrite_paragraph

    with pytest.raises(ValueError, match="out of range"):
        await rewrite_paragraph(SCRIPT_CONTENT, paragraph_index=-1, instruction="test")


async def test_rewrite_paragraph_empty_sections_raises():
    """空 sections 时抛出 ValueError"""
    from app.services.script_service import rewrite_paragraph

    empty_content = {**SCRIPT_CONTENT, "sections": []}
    with pytest.raises(ValueError):
        await rewrite_paragraph(empty_content, paragraph_index=0, instruction="test")


def test_apply_rewrite_updates_correct_section():
    """apply_rewrite 只修改指定段落，其他段落不变"""
    from app.services.script_service import apply_rewrite

    new_content = apply_rewrite(SCRIPT_CONTENT, paragraph_index=1, rewritten_text="全新内容")

    assert new_content["sections"][1]["content"] == "全新内容"
    # 其他段落不受影响
    assert new_content["sections"][0]["content"] == SCRIPT_CONTENT["sections"][0]["content"]
    assert new_content["sections"][2]["content"] == SCRIPT_CONTENT["sections"][2]["content"]
    # 原始对象不被修改（深拷贝验证）
    assert SCRIPT_CONTENT["sections"][1]["content"] == "今天分享5个我用了3年的效率工具，帮你把工作时间缩短30%。"


def test_apply_rewrite_does_not_mutate_original():
    """apply_rewrite 不修改原 content 对象"""
    from app.services.script_service import apply_rewrite

    original_text = SCRIPT_CONTENT["sections"][0]["content"]
    apply_rewrite(SCRIPT_CONTENT, paragraph_index=0, rewritten_text="新文本")
    assert SCRIPT_CONTENT["sections"][0]["content"] == original_text


async def test_rewrite_paragraph_middle_index():
    """改写中间段落（index=1）正确取到对应 section"""
    from app.services.script_service import rewrite_paragraph

    with patch("app.services.script_service.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            return_value=make_llm_resp("改写后的核心方法")
        )
        result = await rewrite_paragraph(SCRIPT_CONTENT, paragraph_index=1, instruction="更简短")

    assert result["section_title"] == "核心方法"
    assert result["original"] == SCRIPT_CONTENT["sections"][1]["content"]
