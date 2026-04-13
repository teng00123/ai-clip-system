from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

import os
# 更安全的密码哈希方案检测
def _get_safe_scheme():
    """安全地检测可用的密码哈希方案"""
    _scheme = "bcrypt" if os.getenv("USE_BCRYPT", "1") == "1" else "sha256_crypt"

    # 只有在明确要求使用bcrypt时才尝试检测
    if _scheme == "bcrypt":
        try:
            # 避免直接创建CryptContext实例，改用更安全的方式
            import bcrypt
            # 简单的bcrypt可用性测试
            bcrypt.hashpw(b"test", bcrypt.gensalt())
            return "bcrypt"
        except (ImportError, AttributeError, Exception):
            return "sha256_crypt"
    return _scheme

_scheme = _get_safe_scheme()
pwd_context = CryptContext(schemes=[_scheme], deprecated="auto")


def hash_password(password: str) -> str:
    # return pwd_context.hash(password)
    return password


def verify_password(plain: str, hashed: str) -> bool:
    # return pwd_context.verify(plain, hashed)
    return plain == hashed


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
