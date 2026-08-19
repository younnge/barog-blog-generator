"""글 생성 3단 파이프라인 — 키워드 → 제목 → 본문 (+ 문단 재생성).

모드 강제는 전부 여기서 한다. 프론트가 입력란을 숨기는 것은 편의일 뿐이고,
정보성 모드로 들어온 요청은 cta 가 실려 있어도 서버가 비운다 (SPEC §5.6).
우회 경로를 만들지 않는다 (CLAUDE.md 절대 규칙 3).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import config_store, llm, prompts, settings
from .auth import guard_generation

router = APIRouter()


# --- 요청 모양 -----------------------------------------------------------

class BaseRequest(BaseModel):
    """모든 생성 요청이 공유하는 입력."""

    mode: str = Field(default=prompts.MODE_INFORMATION, max_length=20)
    lang: str = Field(default=prompts.LANG_KO, max_length=10)

    branch: str = Field(default="", max_length=60)
    procedure: str = Field(default="", max_length=60)
    persona: str = Field(default="", max_length=60)
    persona_custom: str = Field(default="", max_length=300)
    audience: str = Field(default="", max_length=60)
    tone: str = Field(default="", max_length=60)
    platform: str = Field(default="", max_length=60)
    length: str = Field(default="medium", max_length=20)

    reference: str = Field(default="", max_length=8000)
    cta: str = Field(default="", max_length=500)


class KeywordsRequest(BaseRequest):
    pass


class TitlesRequest(BaseRequest):
    selected_keywords: list[str] = Field(default_factory=list, max_length=10)


class DraftRequest(TitlesRequest):
    title: str = Field(default="", max_length=200)


class SectionRequest(DraftRequest):
    heading: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=4000)
    instruction: str = Field(default="", max_length=300)


# --- 공통 준비 -----------------------------------------------------------

def _load_config() -> dict[str, Any]:
    try:
        return config_store.load_all()
    except config_store.ConfigError as exc:
        raise HTTPException(
            status_code=503,
            detail="선택 목록을 불러오지 못했어요. 잠시 뒤에 새로고침해 주세요.",
        ) from exc


def _prepare(req: BaseRequest) -> tuple[str, dict[str, Any], str]:
    """모드를 확정하고 맥락을 만든다. 반환: (모드, 맥락, 브리핑 문자열)

    여기서 정보성 모드의 금지 요소를 실제로 제거한다.
    """
    mode = req.mode if req.mode in prompts.MODES else prompts.MODE_INFORMATION
    lang = req.lang if req.lang in prompts.LANGS else prompts.LANG_KO

    config = _load_config()
    payload = req.model_dump()

    ctx = prompts.build_context(payload, config)

    if ctx["procedure"] is None:
        raise HTTPException(status_code=400, detail="시술을 다시 골라주세요.")

    # 정보성 모드에서 후기형은 선택할 수 없다. 화면에서도 숨기지만 서버에서도 막는다.
    if mode == prompts.MODE_INFORMATION and ctx["persona"] and ctx["persona"].get("id") == "review":
        raise HTTPException(status_code=400, detail="이 글 목적에서는 후기형을 쓸 수 없어요. 글쓴이 시점을 다시 골라주세요.")

    # 정보성 모드에서는 이벤트·가격·CTA 를 통째로 버린다. 프롬프트에 도달하지 못하게 한다.
    if mode == prompts.MODE_INFORMATION:
        payload["cta"] = ""

    brief = prompts.build_brief(payload, ctx, mode)
    ctx["_lang"] = lang
    ctx["_payload"] = payload
    return mode, ctx, brief


def _clean_keywords(values: list[str]) -> list[str]:
    """빈 값·중복을 걸러내고 최대 5개까지만 쓴다."""
    seen: list[str] = []
    for raw in values:
        text = (raw or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen[:5]


def _take(items: Any, limit: int) -> list:
    """개수 상한을 지킨다.

    구조화 출력 스키마에 maxItems 를 쓸 수 없어(API 가 400 으로 거절) 여기서 자른다.
    개수 요청은 프롬프트가 하고, 넘치면 서버가 자른다.
    """
    return list(items or [])[:limit]


def _llm_error(exc: llm.LLMError) -> HTTPException:
    """LLMError 의 한국어 문장을 그대로 화면에 전달한다."""
    return HTTPException(status_code=502, detail=exc.message)


# --- 엔드포인트 ----------------------------------------------------------

@router.post("/api/keywords")
def suggest_keywords(req: KeywordsRequest, _: None = Depends(guard_generation)) -> dict[str, Any]:
    mode, ctx, brief = _prepare(req)
    try:
        data = llm.generate_json(
            model=settings.MODEL_FAST,
            system=prompts.system_prompt(mode, ctx["_lang"]),
            prompt=prompts.keywords_prompt(brief, mode),
            schema=prompts.KEYWORDS_SCHEMA,
            label="키워드",
        )
    except llm.LLMError as exc:
        raise _llm_error(exc) from exc

    return {"keywords": _take(data.get("keywords"), prompts.MAX_KEYWORDS), "mode": mode}


@router.post("/api/titles")
def suggest_titles(req: TitlesRequest, _: None = Depends(guard_generation)) -> dict[str, Any]:
    keywords = _clean_keywords(req.selected_keywords)
    if not keywords:
        raise HTTPException(status_code=400, detail="키워드를 먼저 골라주세요.")

    mode, ctx, brief = _prepare(req)
    try:
        data = llm.generate_json(
            model=settings.MODEL_FAST,
            system=prompts.system_prompt(mode, ctx["_lang"]),
            prompt=prompts.titles_prompt(brief, keywords, mode),
            schema=prompts.TITLES_SCHEMA,
            label="제목",
        )
    except llm.LLMError as exc:
        raise _llm_error(exc) from exc

    # 글자수는 화면에서 쓰므로 서버가 계산해 함께 준다.
    titles = [
        {**item, "char_count": len(item.get("text", ""))}
        for item in _take(data.get("titles"), prompts.MAX_TITLES)
    ]
    return {"titles": titles, "mode": mode}


@router.post("/api/draft")
def create_draft(req: DraftRequest, _: None = Depends(guard_generation)) -> dict[str, Any]:
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="제목을 먼저 골라주세요.")

    keywords = _clean_keywords(req.selected_keywords)
    mode, ctx, brief = _prepare(req)

    length = ctx["length"] or {"target_chars": 2000}
    target_chars = length.get("target_chars", 2000)

    try:
        data = llm.generate_json(
            model=settings.MODEL_MAIN,
            system=prompts.system_prompt(mode, ctx["_lang"]),
            prompt=prompts.draft_prompt(
                brief=brief,
                title=title,
                keywords=keywords,
                target_chars=target_chars,
                platform_id=req.platform,
                mode=mode,
                cta=ctx["_payload"]["cta"],
            ),
            schema=prompts.DRAFT_SCHEMA,
            max_tokens=llm.MAX_TOKENS_DRAFT,
            label="본문",
        )
    except llm.LLMError as exc:
        raise _llm_error(exc) from exc

    sections = _take(data.get("sections"), prompts.MAX_SECTIONS)
    char_count = sum(len(s.get("body", "")) for s in sections)

    return {
        "title": title,
        "sections": sections,
        "hashtags": _take(data.get("hashtags"), prompts.MAX_HASHTAGS),
        "meta_description": data.get("meta_description", ""),
        "char_count": char_count,
        "target_chars": target_chars,
        "mode": mode,
        "lang": ctx["_lang"],
    }


@router.post("/api/draft/section")
def regenerate_section(req: SectionRequest, _: None = Depends(guard_generation)) -> dict[str, Any]:
    if not req.body.strip():
        raise HTTPException(status_code=400, detail="다시 쓸 내용을 찾지 못했어요. 새로고침해 주세요.")

    mode, ctx, brief = _prepare(req)
    try:
        data = llm.generate_json(
            model=settings.MODEL_MAIN,
            system=prompts.system_prompt(mode, ctx["_lang"]),
            prompt=prompts.section_prompt(
                brief=brief,
                title=req.title.strip(),
                heading=req.heading,
                body=req.body,
                instruction=req.instruction,
                mode=mode,
            ),
            schema=prompts.SECTION_SCHEMA,
            label="문단 재생성",
        )
    except llm.LLMError as exc:
        raise _llm_error(exc) from exc

    return {"heading": data.get("heading", ""), "body": data.get("body", "")}
