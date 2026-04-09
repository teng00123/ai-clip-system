import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("MINIO_BUCKET", "ai-clip-test")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_BASE_URL", "https://example.com/v1")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.clip_job import ClipJob
from app.models.guide_session import GuideSession
from app.models.project import Project
from app.models.script import Script
from app.models.user import User
from app.models.video import Video
from app.utils.jwt_utils import create_access_token

# ── shared async engine (single in-memory db across all fixtures) ─────────────
async_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
AsyncTestSession = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture(autouse=True)
async def reset_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db():
    async with AsyncTestSession() as session:
        yield session


@pytest.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── factories ─────────────────────────────────────────────────────────────────

@pytest.fixture
def user_factory(db):
    counter = [0]

    async def _make(email: str, nickname: str | None = None) -> User:
        counter[0] += 1
        user = User(id=f"u{counter[0]}", email=email, password_hash="hashed-pw", nickname=nickname)
        db.add(user)
        await db.flush()
        return user

    return _make


@pytest.fixture
def auth_headers_factory():
    def _headers(user: User) -> dict:
        token = create_access_token(user.id, user.email)
        return {"Authorization": f"Bearer {token}"}
    return _headers


@pytest.fixture
def project_factory(db):
    counter = [0]

    async def _make(user: User, name: str = "Test Project", status: str = "draft") -> Project:
        counter[0] += 1
        project = Project(id=f"proj-{counter[0]}", user_id=user.id, name=name, description="desc", status=status)
        db.add(project)
        await db.flush()
        return project

    return _make


@pytest.fixture
def guide_session_factory(db):
    counter = [0]

    async def _make(project: Project, completed: bool = False, step: int = 0, brief: dict | None = None) -> GuideSession:
        counter[0] += 1
        gs = GuideSession(
            id=f"gs-{counter[0]}", project_id=project.id,
            answers={}, brief=brief or {}, step=step, completed=completed,
        )
        db.add(gs)
        await db.flush()
        return gs

    return _make


@pytest.fixture
def video_factory(db):
    counter = [0]

    async def _make(project: Project, filename: str = "demo.mp4") -> Video:
        counter[0] += 1
        video = Video(
            id=f"vid-{counter[0]}", project_id=project.id, filename=filename,
            source="local", storage_path=f"videos/{project.id}/{filename}",
            duration=12.3, file_size="12345", metadata_={},
        )
        db.add(video)
        await db.flush()
        return video

    return _make


@pytest.fixture
def clip_job_factory(db):
    counter = [0]

    async def _make(project: Project, video: Video, status: str = "pending", output_path: str | None = None) -> ClipJob:
        counter[0] += 1
        job = ClipJob(
            id=f"job-{counter[0]}", project_id=project.id, video_id=video.id,
            status=status, progress=100 if status == "done" else 0, output_path=output_path,
        )
        db.add(job)
        await db.flush()
        return job

    return _make


@pytest.fixture
def script_factory(db):
    counter = [0]

    async def _make(project: Project, version: int = 1, is_latest: bool = True) -> Script:
        counter[0] += 1
        script = Script(
            id=f"scr-{counter[0]}", project_id=project.id, version=version,
            format="voiceover",
            content={"title": "t", "hook": "h", "sections": [], "cta": "c",
                     "total_duration_estimate": "30s", "notes": "n"},
            is_latest=is_latest,
        )
        db.add(script)
        await db.flush()
        return script

    return _make
