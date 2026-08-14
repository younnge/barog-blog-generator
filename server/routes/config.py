"""기준정보 제공 엔드포인트."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from .. import config_store
from .auth import require_token

router = APIRouter()


@router.get("/api/config")
def get_config(_: None = Depends(require_token)) -> dict[str, Any]:
    try:
        return config_store.load_all()
    except config_store.ConfigError as exc:
        # 파일이 없거나 형식이 깨진 경우. 원인은 서버 로그로만 남기고 화면에는 다음 행동을 안내한다.
        raise HTTPException(
            status_code=503,
            detail="선택 목록을 불러오지 못했어요. 잠시 뒤에 새로고침해 주세요.",
        ) from exc
