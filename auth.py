"""
auth.py — Authentication helpers: password hashing, session tokens, current user.
"""

import os
import sqlite3

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

# 30 days in seconds (parent sessions)
_SESSION_MAX_AGE = 60 * 60 * 24 * 30

# 30 minutes in seconds (child sessions — shorter for safety)
_CHILD_SESSION_MAX_AGE = 60 * 30


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def _get_signer() -> TimestampSigner:
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY environment variable is required")
    return TimestampSigner(secret_key)


def create_session_token(user_id: int) -> str:
    signer = _get_signer()
    return signer.sign(str(user_id)).decode()


def decode_session_token(token: str) -> int | None:
    signer = _get_signer()
    try:
        value = signer.unsign(token, max_age=_SESSION_MAX_AGE)
        return int(value.decode())
    except (BadSignature, SignatureExpired, ValueError):
        return None


def get_current_user(request, conn: sqlite3.Connection) -> dict | None:
    """Read kid_session cookie, decode it, return user dict or None."""
    token = request.cookies.get("kid_session")
    if not token:
        return None
    user_id = decode_session_token(token)
    if user_id is None:
        return None
    from db import get_user_by_id
    return get_user_by_id(conn, user_id)


def create_child_session_token(child_id: int) -> str:
    """Sign child_id. Payload: "c{child_id}" (prefix avoids collision with user IDs)."""
    signer = _get_signer()
    return signer.sign(f"c{child_id}").decode()


def decode_child_session_token(token: str) -> int | None:
    """Unsign and decode a child session token. Returns child_id (int) or None on error/expiry."""
    signer = _get_signer()
    try:
        value = signer.unsign(token, max_age=_CHILD_SESSION_MAX_AGE)
        raw = value.decode()
        if not raw.startswith("c"):
            return None
        return int(raw[1:])
    except (BadSignature, SignatureExpired, ValueError):
        return None


def get_current_child(request, conn) -> dict | None:
    """Read kid_session_child cookie, decode it, return child dict (without pin_hash) or None."""
    token = request.cookies.get("kid_session_child")
    if not token:
        return None
    child_id = decode_child_session_token(token)
    if child_id is None:
        return None
    from db import get_child_by_id
    child = get_child_by_id(conn, child_id)
    if child:
        child.pop("pin_hash", None)
    return child
