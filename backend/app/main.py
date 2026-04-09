from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, projects, guide, scripts, videos, clips, ws
from app.database import init_db

app = FastAPI(title="AI Clip System API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(guide.router, prefix="/api")
app.include_router(scripts.router, prefix="/api")
app.include_router(videos.router, prefix="/api")
app.include_router(clips.router, prefix="/api")
app.include_router(ws.router)


@app.on_event("startup")
async def startup():
    await init_db()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-clip-api"}
