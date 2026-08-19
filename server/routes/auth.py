"""잠금 화면 인증.

비밀번호 검증은 반드시 서버에서 한다. 프론트로 비밀번호나 해시를 내려보내지 않는다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .. import security, settings

router = APIRouter()

# auto_error=False: 헤더가 없을 때도 우리가 만든 한국어 안내로 응답하기 위함.
_bearer = HTTPBearer(auto_error=False)


class AuthRequest(BaseModel):
    password: str = Field(default="", max_length=200)


class AuthResponse(BaseModel):
    token: str
    expires_at: int


def _client_key(request: Request) -> str:
    """시도 제한에 쓸 클라이언트 식별값. Render는 프록시 뒤에 있어 헤더를 먼저 본다."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/api/auth", response_model=AuthResponse)
def authenticate(payload: AuthRequest, request: Request) -> AuthResponse:
    if settings.missing_required():
        # 배포 설정이 덜 된 상태. 사용자에게는 기술 용어 없이 안내한다.
        raise HTTPException(status_code=503, detail="아직 준비가 덜 됐어요. 관리자에게 알려주세요.")

    client_key = _client_key(request)
    if security.too_many_attempts(client_key):
        raise HTTPException(
            status_code=429,
            detail="비밀번호를 여러 번 잘못 입력했어요. 5분 뒤에 다시 시도해 주세요.",
        )

    if not security.verify_password(payload.password):
        raise HTTPException(status_code=401, detail="비밀번호가 맞지 않아요. 다시 입력해 주세요.")

    security.clear_attempts(client_key)
    token, expires_at = security.issue_token()
    return AuthResponse(token=token, expires_at=expires_at)


def require_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """토큰이 필요한 엔드포인트에 붙이는 의존성."""
    token = credentials.credentials if credentials else ""
    if not security.verify_token(token):
        raise HTTPException(status_code=401, detail="다시 로그인해 주세요.")


def guard_generation(
    request: Request,
    _: None = Depends(require_token),
) -> None:
    """생성·검사 계열 엔드포인트 보호 — 토큰 확인 + IP별 호출량 제한.

    토큰이 유효해도 한 IP가 짧은 시간에 지나치게 많이 부르면 막는다.
    비밀번호가 유출돼도 Claude 호출 비용이 폭주하지 않게 하는 방어선이다.
    """
    if security.too_many_generations(_client_key(request)):
        raise HTTPException(
            status_code=429,
            detail="잠깐 사이에 요청이 너무 많았어요. 30초쯤 뒤에 다시 눌러주세요.",
        )
