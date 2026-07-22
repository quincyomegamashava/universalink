from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from app.core.config import get_settings

pwd_hasher = PasswordHasher()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(subject: str, role: str, extra: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": str(uuid4()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(subject: str, role: str) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": subject,
        "role": role,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


def safe_decode_token(token: str) -> dict[str, Any] | None:
    try:
        return decode_token(token)
    except JWTError:
        return None


def hash_api_key(raw_key: str) -> str:
    return pwd_hasher.hash(raw_key)


def verify_api_key(raw_key: str, key_hash: str) -> bool:
    try:
        return pwd_hasher.verify(key_hash, raw_key)
    except VerifyMismatchError:
        return False


def generate_api_key() -> str:
    return f"sk-ai-{uuid4().hex}{uuid4().hex[:16]}"


def create_password_reset_token(user_id: str) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(hours=1)
    payload = {
        "sub": user_id,
        "type": "password_reset",
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_password_reset_token(token: str) -> dict[str, Any] | None:
    payload = safe_decode_token(token)
    if not payload or payload.get("type") != "password_reset":
        return None
    return payload
