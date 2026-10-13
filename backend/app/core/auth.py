"""Authentication: password hashing and signed session tokens.

Password storage uses PBKDF2-HMAC-SHA256 from the standard library with a
per-password random salt and a high iteration count. That is a NIST-acceptable
scheme and avoids a native-build dependency. If you later move to production,
argon2id (`argon2-cffi`) is the stronger choice -- swap `hash_password` and
`verify_password` and nothing else changes.

Tokens are signed JWTs. The signing key MUST be set via JWT_SECRET in production;
a random key is generated at startup otherwise, which invalidates every session
whenever the server restarts (safe default, obvious symptom).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import User

PBKDF2_ITERATIONS = 480_000
ALGORITHM = "HS256"


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return "$".join([
        "pbkdf2_sha256", str(PBKDF2_ITERATIONS),
        base64.b64encode(salt).decode(), base64.b64encode(digest).decode(),
    ])


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        expected = base64.b64decode(digest_b64)
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), base64.b64decode(salt_b64), int(iterations))
    except (ValueError, TypeError):
        return False
    # Constant-time comparison: never leak how much of the hash matched.
    return hmac.compare_digest(candidate, expected)


def password_problems(password: str) -> list[str]:
    """Readable rules. Kept deliberately modest so the demo is usable."""
    issues = []
    if len(password) < 12:
        issues.append("at least 12 characters")
    if password.isdigit():
        issues.append("not only numbers")
    if password.lower() in {"password", "12345678", "iris1234", "qwertyui"}:
        issues.append("not a common password")
    return issues


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------

def create_access_token(user_id: str, email: str) -> tuple[str, int]:
    expires_in = settings.jwt_expire_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        "iss": "iiris",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM), expires_in


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM], issuer="iiris")


CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not signed in, or the session has expired. Please sign in again.",
    headers={"WWW-Authenticate": "Bearer"},
)


def _token_from_request(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _token_from_request(request)
    if not token:
        raise CREDENTIALS_ERROR
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Your session has expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.PyJWTError as exc:
        raise CREDENTIALS_ERROR from exc

    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise CREDENTIALS_ERROR
    request.state.actor_id = user.user_id
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    try:
        return get_current_user(request, db)
    except HTTPException:
        return None
