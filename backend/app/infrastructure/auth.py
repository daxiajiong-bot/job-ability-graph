"""Authentication utilities: password hashing and JWT tokens."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from base64 import b64decode, b64encode
from typing import Optional

# JWT secret key — loaded from environment
_JWT_SECRET: Optional[str] = None
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24


def _get_jwt_secret() -> str:
    """Lazy-load JWT secret from environment."""
    global _JWT_SECRET
    if _JWT_SECRET is None:
        _JWT_SECRET = os.getenv("JWT_SECRET_KEY", "job-ability-graph-dev-secret-key-change-in-production")
    return _JWT_SECRET


# ── Password hashing (PBKDF2-SHA256) ─────────────────────

def hash_password(password: str) -> str:
    """Hash a password with a random salt using PBKDF2-SHA256.

    Returns: ``salt$hash`` (both base64-encoded).
    """
    salt = os.urandom(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations=100_000)
    return f"{b64encode(salt).decode()}${b64encode(dk).decode()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a ``salt$hash`` string."""
    try:
        salt_b64, hash_b64 = password_hash.split("$", 1)
        salt = b64decode(salt_b64)
        expected = b64decode(hash_b64)
    except (ValueError, Exception):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations=100_000)
    return hmac.compare_digest(dk, expected)


# ── JWT tokens (minimal implementation, no external deps) ──

def _b64url_encode(data: bytes) -> str:
    return b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return b64decode(s)


def create_access_token(user_id: str, role: str, username: str) -> str:
    """Create a minimal HS256 JWT token."""
    import json

    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    now = int(time.time())
    payload = _b64url_encode(json.dumps({
        "sub": user_id,
        "role": role,
        "username": username,
        "iat": now,
        "exp": now + JWT_EXPIRE_HOURS * 3600,
    }).encode())
    signing_input = f"{header}.{payload}"
    signature = hmac.new(
        _get_jwt_secret().encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT token.

    Returns the payload dict on success.
    Raises ``ValueError`` on invalid/expired token.
    """
    import json

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format")

    header, payload, signature = parts
    signing_input = f"{header}.{payload}"
    expected_sig = hmac.new(
        _get_jwt_secret().encode(), signing_input.encode(), hashlib.sha256
    ).digest()

    if not hmac.compare_digest(_b64url_decode(signature), expected_sig):
        raise ValueError("Invalid token signature")

    data = json.loads(_b64url_decode(payload))
    if data.get("exp", 0) < time.time():
        raise ValueError("Token has expired")

    return data
