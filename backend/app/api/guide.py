from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
from app.database import get_db
from app.models.user import User
from app.models.guide_session import GuideSession
from app.schemas.guide_session import AnswerSubmit, QuestionOut, GuideSessionOut
from app.services.guide_service import get_question, generate_brief, TOTAL_STEPS
from app.utils.deps import get_current_user, get_project_for_user, get_guide_session_for_project

router = APIRouter(prefix="/guide", tags=["guide"])


@router.post("/{project_id}/start", response_model=GuideSessionOut)
async def start_guide(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await get_project_for_user(project_id, db, user)
    existing = await db.execute(select(GuideSession).where(GuideSession.project_id == project_id))
    session = existing.scalar_one_or_none()
    if not session:
        session = GuideSession(id=str(uuid.uuid4()), project_id=project_id, answers={}, step=0)
        db.add(session)
        await db.flush()
    return GuideSessionOut.model_validate(session)


@router.get("/{project_id}/question", response_model=QuestionOut)
async def get_current_question(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
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
    )


@router.post("/{project_id}/answer", response_model=GuideSessionOut)
async def submit_answer(project_id: str, data: AnswerSubmit, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
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


@router.get("/{project_id}/brief")
async def get_brief(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    session = await get_guide_session_for_project(project_id, db, user)
    if not session.completed:
        raise HTTPException(status_code=400, detail="Guide not completed yet")
    return session.brief
