"""기준정보(config/*.json) 로딩.

기준정보는 코드에 하드코딩하지 않는다. JSON 파일을 읽어 그대로 내려보내고,
프론트는 그 데이터로 버튼을 그린다. 지점 추가 = JSON 한 줄 추가로 끝나야 한다.

파일 수정시각을 확인해 바뀐 파일만 다시 읽는다(서버 재시작 없이 반영).
"""

from __future__ import annotations

import json
from typing import Any

from .settings import CONFIG_DIR

# 파일명(확장자 제외) -> /api/config 응답에서 쓸 키
CONFIG_FILES = {
    "branches": "branches.json",
    "procedures": "procedures.json",
    "personas": "personas.json",
    "audiences": "audiences.json",
    "tones": "tones.json",
}

# 금지어 사전은 서버에서만 쓴다. /api/config 로 내려보내지 않는다.
# (화면에 사전을 통째로 주면 무엇을 검사하는지 드러나고, 쓸 일도 없다)
COMPLIANCE_FILE = "compliance.json"

# 플랫폼·분량은 출력 포맷·목표 글자수와 직접 묶여 있어 서버가 기준을 갖는다.
# 다만 프론트는 이 값도 API 응답으로 받아 그린다(화면에는 하드코딩하지 않는다).
PLATFORMS = [
    {"id": "naver", "name": "네이버 블로그", "description": "스마트에디터 붙여넣기용", "active": True},
    {"id": "wordpress", "name": "워드프레스·자사 홈페이지", "description": "마크다운 + HTML", "active": True},
    {"id": "sns", "name": "인스타·스레드", "description": "캡션형으로 짧게", "active": True},
    {"id": "blog-md", "name": "티스토리·브런치", "description": "마크다운", "active": True},
]

LENGTHS = [
    {"id": "short", "name": "짧게", "description": "약 1,200자", "target_chars": 1200, "active": True},
    {"id": "medium", "name": "보통", "description": "약 2,000자", "target_chars": 2000, "active": True},
    {"id": "long", "name": "길게", "description": "약 3,000자", "target_chars": 3000, "active": True},
]


class ConfigError(Exception):
    """기준정보 파일을 읽지 못했을 때."""


# {키: (수정시각, 내용)}
_cache: dict[str, tuple[float, Any]] = {}


def _load_file(key: str, filename: str) -> Any:
    path = CONFIG_DIR / filename
    try:
        mtime = path.stat().st_mtime
    except OSError as exc:
        raise ConfigError(f"{filename} 파일을 찾지 못했습니다.") from exc

    cached = _cache.get(key)
    if cached and cached[0] == mtime:
        return cached[1]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"{filename} 파일을 읽지 못했습니다.") from exc

    _cache[key] = (mtime, data)
    return data


def _active_only(items: list[dict]) -> list[dict]:
    """active 가 false 인 항목을 걸러낸다.

    삭제된 지점·시술도 과거 이력 표시를 위해 JSON에는 남겨두므로,
    화면에 그릴 목록에서만 제외한다. active 키가 없으면 노출로 본다.
    """
    return [item for item in items if item.get("active", True)]


def _active_procedures(categories: list[dict]) -> list[dict]:
    """카테고리와 그 안의 시술을 모두 active 기준으로 거른다."""
    result = []
    for category in _active_only(categories):
        pruned = dict(category)
        pruned["items"] = _active_only(category.get("items", []))
        result.append(pruned)
    return result


def load_compliance() -> dict[str, Any]:
    """금지어 사전. 파일을 고치면 서버 재시작 없이 반영된다."""
    return _load_file("compliance", COMPLIANCE_FILE)


def load_all() -> dict[str, Any]:
    """프론트가 화면을 그리는 데 필요한 기준정보 전체."""
    branches = _active_only(_load_file("branches", CONFIG_FILES["branches"]))
    procedures = _active_procedures(_load_file("procedures", CONFIG_FILES["procedures"]))

    payload: dict[str, Any] = {
        "branches": branches,
        "procedures": procedures,
        "platforms": PLATFORMS,
        "lengths": LENGTHS,
    }
    for key in ("personas", "audiences", "tones"):
        payload[key] = _active_only(_load_file(key, CONFIG_FILES[key]))

    payload["counts"] = {
        "branches": len(branches),
        "procedure_categories": len(procedures),
        "procedures": sum(len(c["items"]) for c in procedures),
    }
    return payload
