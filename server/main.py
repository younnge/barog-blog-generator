"""바로그 블로그 글 생성기 — 백엔드 진입점.

Phase 1 범위: 인증 · 기준정보 제공 · 글 생성(키워드/제목/본문) · 상태 확인.
의료법 검사와 이력 저장은 4·6단계에서 붙인다.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from . import settings
from .routes import auth as auth_routes
from .routes import config as config_routes
from .routes import generate as generate_routes

logger = logging.getLogger("barog")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버가 뜰 때 배포 설정이 빠지지 않았는지 로그로 알려준다."""
    missing = settings.missing_required()
    if missing:
        logger.warning("환경변수가 설정되지 않았습니다: %s — 로그인이 동작하지 않습니다.", ", ".join(missing))
    if not settings.ALLOWED_ORIGINS:
        logger.warning("ALLOWED_ORIGINS 가 비어 있습니다 — 배포된 화면에서 호출이 막힙니다.")
    yield


app = FastAPI(
    title="바로그 블로그 글 생성기 API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,       # 사내 도구라 문서 페이지는 공개하지 않는다
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS + settings.LOCAL_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=3600,
)

app.include_router(auth_routes.router)
app.include_router(config_routes.router)
app.include_router(generate_routes.router)


# --- 에러 응답 -----------------------------------------------------------
# 사용자에게는 상태코드·예외명 같은 기술 용어를 보여주지 않는다.
# 화면은 항상 message 필드의 한국어 문장만 읽어 쓰면 된다.

# 우리가 던진 HTTPException 은 detail 에 한국어 문장이 들어 있다.
# 반면 FastAPI·Starlette 이 스스로 던지는 것(잘못된 JSON 본문 등)은 영문이므로 그대로 쓰면 안 된다.
_FRAMEWORK_MESSAGES = {
    "There was an error parsing the body": "입력한 내용을 다시 확인해 주세요.",
    "Not Found": "찾을 수 없는 주소예요.",
    "Method Not Allowed": "잘못된 요청이에요. 새로고침해 주세요.",
}


def _korean_only(detail: object) -> str:
    """화면에 보여줄 한국어 문장을 고른다. 영문이 섞이면 기본 문장으로 바꾼다."""
    if not isinstance(detail, str) or not detail.strip():
        return "잠시 문제가 생겼어요. 다시 눌러볼까요?"
    if detail in _FRAMEWORK_MESSAGES:
        return _FRAMEWORK_MESSAGES[detail]
    # 한글이 하나도 없으면 프레임워크가 만든 영문 메시지로 본다.
    if not any("가" <= ch <= "힣" for ch in detail):
        return "잠시 문제가 생겼어요. 다시 눌러볼까요?"
    return detail


# StarletteHTTPException 으로 등록해야 FastAPI 가 스스로 던지는 것까지 함께 잡힌다.
# (FastAPI 의 HTTPException 은 이것을 상속한다)
@app.exception_handler(StarletteHTTPException)
def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = _korean_only(exc.detail)
    if message == "잠시 문제가 생겼어요. 다시 눌러볼까요?":
        logger.info("변환한 오류 응답: %s %s -> %s", request.url.path, exc.status_code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"message": message})


@app.exception_handler(RequestValidationError)
def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.info("잘못된 요청 형식: %s %s", request.url.path, exc.errors())
    return JSONResponse(
        status_code=400,
        content={"message": "입력한 내용을 다시 확인해 주세요."},
    )


@app.exception_handler(Exception)
def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("처리하지 못한 오류: %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"message": "잠시 문제가 생겼어요. 다시 눌러볼까요?"},
    )


# --- 상태 확인 -----------------------------------------------------------

@app.get("/api/health")
def health() -> dict[str, object]:
    """서버 깨우기 겸 상태 확인용. 무료 플랜은 첫 호출에 시간이 걸릴 수 있다."""
    return {"status": "ok", "ready": not settings.missing_required()}


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "바로그 블로그 글 생성기 서버입니다."}
