"""바로그 블로그 글 생성기 — 백엔드 진입점.

Phase 1 / 1단계 범위: 인증 · 기준정보 제공 · 상태 확인.
글 생성(Claude API)은 3단계에서 붙인다.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from . import settings
from .routes import auth as auth_routes
from .routes import config as config_routes

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


# --- 에러 응답 -----------------------------------------------------------
# 사용자에게는 상태코드·예외명 같은 기술 용어를 보여주지 않는다.
# 화면은 항상 message 필드의 한국어 문장만 읽어 쓰면 된다.

@app.exception_handler(HTTPException)
def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "잠시 문제가 생겼어요. 다시 눌러볼까요?"
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
