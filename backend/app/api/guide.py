"""
引导问答路由

支持两种模式：
- static（默认）：固定题库 8 题，OPENAI_API_KEY 为空时自动使用
- dynamic：LLM 上下文感知多轮问答，6～10 题，需要 OPENAI_API_KEY

端点设计：
- POST   /{project_id}/start           — 创建/重置会话（自动选模式）
- GET    /{project_id}/question         — 静态模式：获取当前问题
- POST   /{project_id}/answer           — 静态模式：提交答案
- POST   /{project_id}/dynamic/start    — 动态模式：开始，返回第一个问题
- POST   /{project_id}/dynamic/answer   — 动态模式：提交答案，返回下一问题
- GET    /{project_id}/brief            — 获取最终 Brief（两种模式通用）
- GET    /{project_id}/mode             — 查询当前可用模式
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from app.database import get_db
from app.models.user import User
from app.models.guide_session import GuideSession
from app.schemas.guide_session import (
    AnswerSubmit,
    QuestionOut,
    GuideSessionOut,
    DynamicAnswerSubmit,
    DynamicQuestionOut,
)
from app.services.guide_service import get_question, generate_brief, TOTAL_STEPS
from app.services.dynamic_qa_service import (
    get_next_question,
    generate_brief_from_history,
    is_dynamic_mode_available,
)
from app.utils.deps import get_current_user, get_project_for_user, get_guide_session_for_project

router = APIRouter(prefix="/guide", tags=["guide"])


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_or_create_session(project_id: str, db: AsyncSession) -> GuideSession:
    existing = await db.execute(select(GuideSession).where(GuideSession.project_id == project_id))
    session = existing.scalar_one_or_none()
    if not session:
        mode = "dynamic" if is_dynamic_mode_available() else "static"
        session = GuideSession(
            id=str(uuid.uuid4()),
            project_id=project_id,
            answers={},
            step=0,
            mode=mode,
            conversation_history=[],
        )
        db.add(session)
        await db.flush()
    return session


# ── Common ─────────────────────────────────────────────────────────────────────

@router.post("/{project_id}/start", response_model=GuideSessionOut)
async def start_guide(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建或获取引导会话，自动根据 OPENAI_API_KEY 决定模式"""
    await get_project_for_user(project_id, db, user)
    session = await _get_or_create_session(project_id, db)
    return GuideSessionOut.model_validate(session)


@router.get("/{project_id}/session", response_model=GuideSessionOut)
async def get_session(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取当前会话，不存在时自动创建（兜底容错）"""
    await get_project_for_user(project_id, db, user)
    session = await _get_or_create_session(project_id, db)
    await db.refresh(session)  # 确保加载所有字段
    return GuideSessionOut.model_validate(session)


@router.get("/{project_id}/dynamic/available")
async def dynamic_available(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[前端]检查动态模式是否可用"""
    await get_project_for_user(project_id, db, user)
    return {"available": is_dynamic_mode_available()}


@router.get("/{project_id}/mode")
async def get_mode(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """查询当前项目引导会话的模式及动态模式可用性"""
    await get_project_for_user(project_id, db, user)
    return {
        "dynamic_available": is_dynamic_mode_available(),
        "recommended_mode": "dynamic" if is_dynamic_mode_available() else "static",
    }


@router.get("/{project_id}/brief")
async def get_brief(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取已完成的 Brief（静态/动态模式通用）"""
    session = await get_guide_session_for_project(project_id, db, user)
    if not session.completed:
        raise HTTPException(status_code=400, detail="Guide not completed yet")
    return session.brief


# ── Static mode ────────────────────────────────────────────────────────────────

@router.get("/{project_id}/question", response_model=QuestionOut)
async def get_current_question(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[静态模式] 获取当前步骤问题"""
    session = await get_guide_session_for_project(project_id, db, user)
    q = get_question(session.step)
    if not q:
        raise HTTPException(status_code=400, detail="All questions completed")
    return QuestionOut(
        step=q["step"],
        total_steps=q["total_steps"],
        question_text=q["display"],
        question_type=q["question_type"],
        options=q["options"],
        is_dynamic=False,
    )


@router.post("/{project_id}/answer", response_model=GuideSessionOut)
async def submit_answer(
    project_id: str,
    data: AnswerSubmit,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """[静态模式] 提交答案，前进到下一步"""
    session = await get_guide_session_for_project(project_id, db, user)

    answers = dict(session.answers or {})
    answers[str(data.step)] = data.answer
    session.answers = answers

    next_step = data.step + 1
    if next_step >= TOTAL_STEPS:
        session.step = TOTAL_STEPS
        session.completed = True
        session.brief = generate_brief(answers)
        project = await get_project_for_user(project_id, db, user)
        if project.status == "draft":
            project.status = "scripting"
    else:
        session.step = next_step

    await db.flush()
    return GuideSessionOut.model_validate(session)


# ── Dynamic mode ───────────────────────────────────────────────────────────────

@router.post("/{project_id}/dynamic/start", response_model=DynamicQuestionOut)
async def dynamic_start(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    [动态模式] 开始问答，返回第一个问题。
    OPENAI_API_KEY 未配置时返回 503。
    """
    if not is_dynamic_mode_available():
        raise HTTPException(
            status_code=503,
            detail="Dynamic mode unavailable: OPENAI_API_KEY not configured. Use static mode instead.",
        )

    await get_project_for_user(project_id, db, user)
    session = await _get_or_create_session(project_id, db)

    # 若已有对话历史，从当前状态继续；否则重新开始
    history = list(session.conversation_history or [])

    try:
        result = await get_next_question(history, answers_count=0)
    except Exception as e:
        err = str(e)
        if "OPENAI_API_KEY" in err or "API Key" in err or "api_key" in err.lower() or "Unauthorized" in err or "401" in err:
            raise HTTPException(status_code=503, detail="AI 服务认证失败，请检查 OPENAI_API_KEY 是否正确")
        if "空内容" in err or "empty" in err.lower():
            raise HTTPException(status_code=503, detail="AI 服务返回空内容，请检查 OPENAI_API_KEY 和 OPENAI_BASE_URL 配置")
        raise HTTPException(status_code=502, detail=f"LLM 调用失败：{err}")

    # 将 assistant 的第一个问题追加到历史
    if result["question"]:
        history.append({"role": "assistant", "content": result["question"]})
        session.conversation_history = history
        session.mode = "dynamic"
        await db.flush()

    return DynamicQuestionOut(
        question=result["question"],
        question_type=result.get("question_type", "text_input"),
        options=result.get("options"),
        is_complete=result.get("is_complete", False),
        answers_count=0,
        mode="dynamic",
    )


@router.post("/{project_id}/dynamic/answer", response_model=DynamicQuestionOut)
async def dynamic_answer(
    project_id: str,
    data: DynamicAnswerSubmit,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    [动态模式] 提交答案，LLM 据此生成下一个问题。

    - 若 is_complete=true：自动生成 Brief，更新项目状态为 scripting
    - 对话历史存储在 conversation_history 字段
    """
    if not is_dynamic_mode_available():
        raise HTTPException(
            status_code=503,
            detail="Dynamic mode unavailable: OPENAI_API_KEY not configured.",
        )

    session = await get_guide_session_for_project(project_id, db, user)

    if session.completed:
        raise HTTPException(status_code=400, detail="Guide already completed")

    # 1. 把用户回答追加到对话历史
    history = list(session.conversation_history or [])
    history.append({"role": "user", "content": data.answer})

    # 2. 记录到 answers（用轮次作为 key，保持与静态模式兼容）
    answers_count = sum(1 for m in history if m["role"] == "user")
    answers = dict(session.answers or {})
    answers[str(answers_count - 1)] = data.answer
    session.answers = answers

    # 3. 调用 LLM 获取下一问题
    try:
        result = await get_next_question(history, answers_count=answers_count)
    except Exception as e:
        err = str(e)
        if "OPENAI_API_KEY" in err or "API Key" in err or "api_key" in err.lower() or "Unauthorized" in err or "401" in err:
            raise HTTPException(status_code=503, detail="AI 服务认证失败，请检查 OPENAI_API_KEY 是否正确")
        if "空内容" in err or "empty" in err.lower():
            raise HTTPException(status_code=503, detail="AI 服务返回空内容，请检查 OPENAI_API_KEY 和 OPENAI_BASE_URL 配置")
        raise HTTPException(status_code=502, detail=f"LLM 调用失败：{err}")

    is_complete = result.get("is_complete", False)

    if is_complete:
        # 4a. 对话结束：生成 Brief
        session.conversation_history = history
        session.completed = True
        session.step = answers_count

        try:
            brief = await generate_brief_from_history(history)
        except Exception:
            # Brief 生成失败时用 answers 兜底
            from app.services.guide_service import generate_brief
            brief = generate_brief(answers)

        session.brief = brief

        # 更新项目状态
        project = await get_project_for_user(project_id, db, user)
        if project.status == "draft":
            project.status = "scripting"

        await db.flush()
        return DynamicQuestionOut(
            question="",
            question_type="text_input",
            options=None,
            is_complete=True,
            answers_count=answers_count,
            mode="dynamic",
        )
    else:
        # 4b. 继续追问：追加 assistant 问题到历史
        next_question = result.get("question", "")
        if next_question:
            history.append({"role": "assistant", "content": next_question})

        session.conversation_history = history
        session.step = answers_count
        await db.flush()

        return DynamicQuestionOut(
            question=next_question,
            question_type=result.get("question_type", "text_input"),
            options=result.get("options"),
            is_complete=False,
            answers_count=answers_count,
            mode="dynamic",
        )
