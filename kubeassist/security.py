"""Signed, short-lived bearer tokens that bind a browser to a server-side session."""
from __future__ import annotations

import datetime as dt
import hmac
import secrets
from functools import wraps

import jwt
from flask import current_app, g, jsonify, request

ALGORITHM = "HS256"


def new_subject() -> str:
    return f"visitor-{secrets.token_hex(6)}"


def issue_token(secret: str, subject: str, ttl_hours: int) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    claims = {"sub": subject, "iat": now, "exp": now + dt.timedelta(hours=ttl_hours)}
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def read_token(secret: str, token: str) -> str | None:
    """Return the token subject, or ``None`` if it is invalid or expired."""
    try:
        return jwt.decode(token, secret, algorithms=[ALGORITHM])["sub"]
    except jwt.PyJWTError:
        return None


def access_code_matches(expected: str | None, supplied: str | None) -> bool:
    if not expected:
        return True
    return hmac.compare_digest(expected.encode(), (supplied or "").encode())


def login_required(view):
    """Reject requests that lack a valid bearer token; expose it as ``g.session_id``."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return jsonify(error="Missing bearer token."), 401
        subject = read_token(current_app.config["SETTINGS"].secret_key, token.strip())
        if subject is None:
            return jsonify(error="Invalid or expired token."), 401
        g.session_id = subject
        return view(*args, **kwargs)

    return wrapper


class RateLimiter:
    """Tiny in-memory sliding-window limiter (per client address, per process)."""

    def __init__(self, per_minute: int):
        import threading
        from collections import defaultdict, deque

        self.per_minute = per_minute
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        import time

        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            return True
