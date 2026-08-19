"""Claude API 호출 래퍼.

API 키는 환경변수에서만 읽고 어떤 응답에도 실어 보내지 않는다 (CLAUDE.md 절대 규칙 1).
호출 실패는 전부 LLMError 로 바꿔서 올린다. LLMError 의 메시지는 그대로 화면에
보여줄 수 있는 한국어 문장이며, 상태코드·예외명 같은 기술 용어를 담지 않는다
(CLAUDE.md 절대 규칙 4).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from . import settings

logger = logging.getLogger("barog.llm")

# 단계별 출력 상한. 넉넉히 잡되 본문만 크게 준다.
MAX_TOKENS_SHORT = 4000    # 키워드·제목·문단 재생성
MAX_TOKENS_DRAFT = 16000   # 본문 전체


class LLMError(Exception):
    """글 생성에 실패했을 때. message 는 그대로 사용자에게 보여줄 한국어 문장이다."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """클라이언트는 한 번만 만들어 재사용한다(연결 재사용)."""
    global _client
    if _client is None:
        if not settings.ANTHROPIC_API_KEY:
            raise LLMError("아직 준비가 덜 됐어요. 관리자에게 알려주세요.")
        _client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=float(settings.LLM_TIMEOUT_SECONDS),
            max_retries=2,
        )
    return _client


def generate_json(
    *,
    model: str,
    system: str,
    prompt: str,
    schema: dict[str, Any],
    max_tokens: int = MAX_TOKENS_SHORT,
    label: str = "",
) -> dict[str, Any]:
    """구조화 출력으로 JSON 을 받아 dict 로 돌려준다.

    schema 로 응답 모양을 강제하므로 파싱 실패가 사실상 없다.
    그래도 만에 하나 깨지면 LLMError 로 바꿔 올린다.
    """
    client = _get_client()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.RateLimitError as exc:
        logger.warning("%s: 호출량 제한", label or model)
        raise LLMError("지금 요청이 몰려 있어요. 30초 뒤에 다시 눌러주세요.") from exc
    except anthropic.APITimeoutError as exc:
        logger.warning("%s: 응답 시간 초과", label or model)
        raise LLMError("글을 만드는 데 시간이 너무 오래 걸렸어요. 다시 눌러볼까요?") from exc
    except anthropic.AuthenticationError as exc:
        # 키가 잘못됐거나 만료된 경우. 사용자가 할 수 있는 일이 없으므로 관리자를 부르게 한다.
        logger.error("%s: 인증 실패 — ANTHROPIC_API_KEY 를 확인해야 합니다", label or model)
        raise LLMError("아직 준비가 덜 됐어요. 관리자에게 알려주세요.") from exc
    except anthropic.APIStatusError as exc:
        logger.error("%s: 응답 오류 (status=%s)", label or model, exc.status_code)
        raise LLMError("잠시 문제가 생겼어요. 다시 눌러볼까요?") from exc
    except anthropic.APIConnectionError as exc:
        logger.warning("%s: 연결 실패", label or model)
        raise LLMError("연결이 잠시 끊겼어요. 다시 눌러볼까요?") from exc

    # 안전 분류기가 요청을 거절한 경우. 정상 응답(200)으로 오므로 따로 확인한다.
    if response.stop_reason == "refusal":
        logger.info("%s: 모델이 응답을 거절했습니다", label or model)
        raise LLMError("이 조건으로는 글을 만들기 어려워요. 시술이나 톤을 바꿔서 다시 시도해 주세요.")

    if response.stop_reason == "max_tokens":
        logger.warning("%s: 출력 길이 상한에 걸렸습니다", label or model)
        raise LLMError("글이 너무 길어져서 중간에 끊겼어요. 분량을 줄여서 다시 시도해 주세요.")

    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("%s: 응답을 해석하지 못했습니다", label or model)
        raise LLMError("결과를 정리하지 못했어요. 다시 눌러볼까요?") from exc

    if not isinstance(data, dict):
        logger.error("%s: 예상과 다른 응답 모양", label or model)
        raise LLMError("결과를 정리하지 못했어요. 다시 눌러볼까요?")

    usage = response.usage
    logger.info(
        "%s 완료 model=%s in=%s out=%s",
        label or "생성", model, usage.input_tokens, usage.output_tokens,
    )
    return data
