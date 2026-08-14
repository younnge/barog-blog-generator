"""환경변수 설정.

비밀번호·서명키 같은 민감한 값은 전부 여기서 환경변수로만 읽는다.
코드나 저장소에 실제 값을 적지 않는다.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 저장소 루트 (server/ 의 상위). config/*.json 을 찾는 기준 경로.
ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"

# 로컬 테스트 편의: server/.env 가 있으면 읽는다.
# Render 에서는 이 파일이 없고 대시보드 환경변수가 그대로 쓰인다.
load_dotenv(ROOT_DIR / "server" / ".env")


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# --- 인증 ---------------------------------------------------------------

# 공통 비밀번호. 평문(APP_PASSWORD) 또는 SHA-256 해시(APP_PASSWORD_SHA256) 중 하나로 지정한다.
# 해시를 넣어두면 Render 대시보드에도 평문이 남지 않는다.
APP_PASSWORD = _env("APP_PASSWORD")
APP_PASSWORD_SHA256 = _env("APP_PASSWORD_SHA256").lower()

# 토큰 서명키. 값이 바뀌면 발급된 토큰이 전부 무효가 된다(= 전원 재로그인).
SESSION_SECRET = _env("SESSION_SECRET")

# 토큰 유효기간 (SPEC: 30일)
TOKEN_TTL_DAYS = _env_int("TOKEN_TTL_DAYS", 30)

# 비밀번호 시도 제한 (한 IP 기준)
AUTH_MAX_ATTEMPTS = _env_int("AUTH_MAX_ATTEMPTS", 10)
AUTH_WINDOW_SECONDS = _env_int("AUTH_WINDOW_SECONDS", 300)

# --- CORS ---------------------------------------------------------------

# 쉼표로 구분. 예) https://younnge.github.io
ALLOWED_ORIGINS = [o for o in (x.strip() for x in _env("ALLOWED_ORIGINS").split(",")) if o]

# 로컬 개발용 오리진은 항상 허용한다(정적 파일을 로컬 서버로 띄워 확인하기 위함).
LOCAL_ORIGINS = [
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# --- 상태 ---------------------------------------------------------------

def missing_required() -> list[str]:
    """설정이 빠져서 서비스가 정상 동작할 수 없는 항목 목록."""
    missing = []
    if not APP_PASSWORD and not APP_PASSWORD_SHA256:
        missing.append("APP_PASSWORD")
    if not SESSION_SECRET:
        missing.append("SESSION_SECRET")
    return missing
