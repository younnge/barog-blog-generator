"""의료법 표현 검사.

2중으로 본다.
  1차 — 금지어 사전(config/compliance.json) 규칙 매칭. 즉시·무료.
  2차 — Claude 문맥 판정. 규칙으로 못 잡는 것(체험담 서술, 진단적 표현 등).

등급은 글 목적(모드)에 따라 달라진다. 예를 들어 가격 표기는
정보성에서는 🔴위험, 홍보성에서는 🟡주의다 (SPEC §6.3).

이 기능은 보조 도구이며 법률 자문이 아니다.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from . import config_store, llm, prompts, settings

logger = logging.getLogger("barog.compliance")

LEVEL_ORDER = {"danger": 0, "warn": 1, "info": 2}

# 2차 판정을 맡길 항목. 규칙으로는 문맥을 볼 수 없는 것들이다.
LLM_CHECK_PROMPT = """아래는 피부과 블로그 글이다. 한국 의료광고 규정에 걸릴 표현을 찾아라.

[찾을 것 — 문맥을 봐야 알 수 있는 것들]
1. 환자 개인의 치료 경험을 사실처럼 서술한 부분 (치료경험담)
2. 진단이나 처방으로 읽힐 수 있는 단정 ('당신은 OO입니다', 'OO를 받으셔야 합니다')
3. 효과를 단정하는 서술 (가능성이 아니라 확정으로 말하는 것)
4. 의료인의 자격·권위를 오인하게 할 수 있는 표현
5. 지역명과 시술명을 부자연스럽게 반복해 검색 어뷰징으로 보일 수 있는 부분
6. 다른 의료기관을 깎아내리는 표현

[찾지 말 것]
- 단순한 정보 전달, 시술 원리 설명, 일반적인 주의사항 안내
- '개인차가 있습니다', '도움이 될 수 있습니다' 처럼 이미 완곡하게 쓴 표현
- 이미 조심스럽게 쓴 문장을 굳이 문제 삼지 않는다. 확실히 걸릴 것만 집어라.

[규칙]
- phrase 는 **본문에 있는 그대로** 옮긴다. 한 글자도 바꾸지 않는다. 5~40자 사이로 짧게 끊는다.
- reason 은 왜 문제인지 한 문장. 비개발자가 읽는다. 법률 용어를 남발하지 않는다.
- suggestion 은 그 자리에 바로 넣을 수 있는 대체 문구. phrase 와 같은 자리에 들어가야 자연스러워야 한다.
- level 은 'danger'(명백한 위반 소지) 또는 'warn'(해석에 따라 문제) 중 하나.
- 문제가 없으면 빈 배열을 돌려준다. 억지로 만들어내지 않는다.
- 최대 6개까지만 찾는다.

[글 목적]
{mode_note}

[검사할 본문]
---
{text}
---"""

LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "phrase": {"type": "string"},
                    "reason": {"type": "string"},
                    "suggestion": {"type": "string"},
                    "level": {"type": "string", "enum": ["danger", "warn"]},
                },
                "required": ["phrase", "reason", "suggestion", "level"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["issues"],
    "additionalProperties": False,
}

MODE_NOTES = {
    prompts.MODE_INFORMATION: (
        "정보성 글이다. 가격·이벤트·할인·예약 유도가 하나라도 있으면 위반이다."
    ),
    prompts.MODE_PROMOTION: (
        "홍보성 글이다. 이벤트 고지와 예약 유도 자체는 허용된다. "
        "다만 진료비를 쓸 때 조건(부가세 포함 여부 등)이 빠졌거나, "
        "과도한 할인 강조·금품 제공성 표현이 있으면 문제로 본다."
    ),
}


def _load_rules() -> list[dict[str, Any]]:
    """금지어 사전을 읽는다. 파일이 없거나 깨졌으면 빈 목록으로 넘어간다.

    사전을 못 읽었다고 검사를 통째로 실패시키지 않는다. 2차 판정은 계속 돌아야 한다.
    """
    try:
        data = config_store.load_compliance()
    except config_store.ConfigError:
        logger.error("금지어 사전을 읽지 못했습니다 — 규칙 검사를 건너뜁니다")
        return []
    return data.get("rules", [])


def check_rules(text: str, mode: str) -> list[dict[str, Any]]:
    """1차 — 금지어 사전 매칭."""
    issues: list[dict[str, Any]] = []
    seen: set[str] = set()

    for rule in _load_rules():
        level = (rule.get("level") or {}).get(mode)
        if not level:
            continue

        found: list[str] = []

        for phrase in rule.get("match", []):
            if phrase and phrase in text:
                found.append(phrase)

        pattern = rule.get("regex")
        if pattern:
            try:
                found.extend(m.group(0) for m in re.finditer(pattern, text))
            except re.error:
                logger.warning("잘못된 정규식 규칙: %s", rule.get("id"))

        for phrase in found:
            if phrase in seen:
                continue
            seen.add(phrase)
            issues.append({
                "level": level,
                "element": rule.get("element", 0),
                "phrase": phrase,
                "reason": rule.get("reason", ""),
                "suggestion": rule.get("suggestion", ""),
                "rule_id": rule.get("id", ""),
                "source": "rule",
                "offset": text.find(phrase),
            })

    return issues


def check_llm(text: str, mode: str) -> list[dict[str, Any]]:
    """2차 — Claude 문맥 판정. 실패하면 빈 목록을 돌려준다.

    2차가 실패했다고 1차 결과까지 버리지 않는다. 다만 화면에는 그 사실을 알린다.
    """
    prompt = LLM_CHECK_PROMPT.format(
        mode_note=MODE_NOTES.get(mode, MODE_NOTES[prompts.MODE_INFORMATION]),
        text=text,
    )
    data = llm.generate_json(
        model=settings.MODEL_FAST,
        system="너는 한국 의료광고 규정을 검토하는 사람이다. 정확한 인용과 실용적인 대안을 제시한다.",
        prompt=prompt,
        schema=LLM_SCHEMA,
        label="의료법 검사",
    )

    issues: list[dict[str, Any]] = []
    for item in data.get("issues", [])[:6]:
        phrase = (item.get("phrase") or "").strip()
        # 본문에 실제로 없는 문구는 버린다. 화면에서 표시도 교체도 못 하기 때문이다.
        if not phrase or phrase not in text:
            logger.info("2차 판정이 본문에 없는 문구를 지목해 버림: %r", phrase[:40])
            continue
        issues.append({
            "level": item.get("level", "warn"),
            "element": 0,
            "phrase": phrase,
            "reason": item.get("reason", ""),
            "suggestion": (item.get("suggestion") or "").strip(),
            "rule_id": "",
            "source": "llm",
            "offset": text.find(phrase),
        })
    return issues


def _dedupe(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 문구가 겹치면 더 무거운 등급만 남긴다.

    한 문구에 대해 규칙과 2차 판정이 둘 다 걸리는 경우가 있다.
    """
    best: dict[str, dict[str, Any]] = {}
    for issue in issues:
        key = issue["phrase"]
        current = best.get(key)
        if current is None or LEVEL_ORDER[issue["level"]] < LEVEL_ORDER[current["level"]]:
            best[key] = issue

    # 위험 → 주의 → 참고 순, 같은 등급 안에서는 본문에 나온 순서대로
    return sorted(best.values(), key=lambda i: (LEVEL_ORDER[i["level"]], i["offset"]))


def check(text: str, mode: str, use_llm: bool = True) -> dict[str, Any]:
    """전체 검사. 화면이 그대로 쓸 수 있는 모양으로 돌려준다."""
    issues = check_rules(text, mode)
    llm_ok = True

    if use_llm and text.strip():
        try:
            issues.extend(check_llm(text, mode))
        except llm.LLMError as exc:
            # 2차가 안 돌아도 1차 결과는 살린다.
            logger.warning("2차 판정 실패 — 규칙 검사 결과만 사용합니다: %s", exc.message)
            llm_ok = False

    issues = _dedupe(issues)
    counts = {"danger": 0, "warn": 0, "info": 0}
    for issue in issues:
        counts[issue["level"]] = counts.get(issue["level"], 0) + 1

    return {
        "issues": issues,
        "counts": counts,
        "blocked": counts["danger"] > 0,
        "context_checked": llm_ok,
        "mode": mode,
    }
