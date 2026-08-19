"""의료법 표현 검사 엔드포인트.

본문을 받아 걸리는 표현을 등급별로 돌려준다.
🔴위험이 하나라도 남아 있으면 blocked: true 로 알리고, 화면은 복사 버튼을 잠근다.
(CLAUDE.md 절대 규칙 3 — 우회 경로를 만들지 않는다)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import compliance, prompts
from .auth import require_token

router = APIRouter()

# 본문 최대 3,000자 + 여유. 너무 긴 입력은 비용과 시간이 커진다.
MAX_TEXT = 20000


class CheckRequest(BaseModel):
    text: str = Field(default="", max_length=MAX_TEXT)
    mode: str = Field(default=prompts.MODE_INFORMATION, max_length=20)
    lang: str = Field(default=prompts.LANG_KO, max_length=10)
    # 문구를 바꾼 뒤 다시 부를 때는 규칙 검사만 돌려 빠르게 확인한다.
    quick: bool = Field(default=False)


@router.post("/api/compliance")
def check_text(req: CheckRequest, _: None = Depends(require_token)) -> dict[str, Any]:
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="검사할 글이 없어요. 본문을 먼저 만들어 주세요.")

    mode = req.mode if req.mode in prompts.MODES else prompts.MODE_INFORMATION
    return compliance.check(text, mode, use_llm=not req.quick)
