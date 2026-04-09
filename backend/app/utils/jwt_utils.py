from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

import os
_scheme = "bcrypt" if os.getenv("USE_BCRYPT", "1") == "1" else "sha256_crypt"
try:
    # verify bcrypt is actually usable in this environment
    _test_ctx = CryptContext(schemes=["bcrypt"])
    _test_ctx.hash("probe")
    _scheme = "bcrypt"
except Exception:
    _scheme = "sha256_crypt"
pwd_context = CryptContext(schemes=[_scheme], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except JWTError:
        return None


def get_bearer_token_from_header(authorization: str | None) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()
