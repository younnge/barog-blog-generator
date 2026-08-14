"""비밀번호 검증 · 세션 토큰 · 시도 제한.

토큰은 외부 라이브러리 없이 HMAC-SHA256 서명 방식으로 직접 만든다.
형식: base64url(payload_json).base64url(signature)
payload 에는 개인정보를 담지 않는다(발급시각·만료시각만).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections import defaultdict, deque

from . import settings


# --- 비밀번호 -----------------------------------------------------------

def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_password(candidate: str) -> bool:
    """입력한 비밀번호가 맞는지 확인한다. 비교는 해시로, 상수시간으로 한다."""
    if not candidate:
        return False

    expected_hash = settings.APP_PASSWORD_SHA256
    if not expected_hash:
        if not settings.APP_PASSWORD:
            return False
        expected_hash = _sha256_hex(settings.APP_PASSWORD)

    return hmac.compare_digest(_sha256_hex(candidate), expected_hash)


# --- 토큰 ---------------------------------------------------------------

def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(payload_b64: str) -> str:
    signature = hmac.new(
        settings.SESSION_SECRET.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64encode(signature)


def issue_token(now: int | None = None) -> tuple[str, int]:
    """세션 토큰과 만료시각(epoch 초)을 돌려준다."""
    issued_at = int(time.time()) if now is None else now
    expires_at = issued_at + settings.TOKEN_TTL_DAYS * 24 * 60 * 60

    payload_b64 = _b64encode(
        json.dumps({"iat": issued_at, "exp": expires_at}, separators=(",", ":")).encode("utf-8")
    )
    return f"{payload_b64}.{_sign(payload_b64)}", expires_at


def verify_token(token: str) -> bool:
    """서명이 유효하고 아직 만료되지 않은 토큰인지 확인한다."""
    if not token or not settings.SESSION_SECRET:
        return False

    parts = token.split(".")
    if len(parts) != 2:
        return False

    payload_b64, signature_b64 = parts
    if not hmac.compare_digest(_sign(payload_b64), signature_b64):
        return False

    try:
        payload = json.loads(_b64decode(payload_b64))
        expires_at = int(payload["exp"])
    except (ValueError, KeyError, TypeError):
        return False

    return time.time() < expires_at


# --- 시도 제한 ----------------------------------------------------------

# {클라이언트 키: 최근 시도 시각들}. 무료 플랜은 단일 인스턴스라 메모리 보관으로 충분하다.
_attempts: dict[str, deque[float]] = defaultdict(deque)


def too_many_attempts(client_key: str) -> bool:
    """짧은 시간에 비밀번호를 반복 시도했는지 확인하고, 시도 횟수를 기록한다."""
    now = time.time()
    window_start = now - settings.AUTH_WINDOW_SECONDS
    history = _attempts[client_key]

    while history and history[0] < window_start:
        history.popleft()

    if len(history) >= settings.AUTH_MAX_ATTEMPTS:
        return True

    history.append(now)
    return False


def clear_attempts(client_key: str) -> None:
    """로그인에 성공하면 기록을 비운다."""
    _attempts.pop(client_key, None)
