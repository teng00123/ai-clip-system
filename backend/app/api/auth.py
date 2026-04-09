from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserOut, TokenOut
from app.utils.jwt_utils import hash_password, verify_password, create_access_token
import uuid

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        id=str(uuid.uuid4()),
        email=data.email,
        password_hash=hash_password(data.password),
        nickname=data.nickname,
    )
    db.add(user)
    await db.flush()
    token = create_access_token(user.id, user.email)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(user.id, user.email)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(db: AsyncSession = Depends(get_db), current_user: User = Depends(__import__("app.utils.deps", fromlist=["get_current_user"]).get_current_user)):
    return UserOut.model_validate(current_user)
