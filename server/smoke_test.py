"""1~4단계 점검 스크립트.

서버를 띄우지 않고 바로 확인한다.

    .venv\\Scripts\\python.exe -m server.smoke_test

배포된 서버를 확인하려면 주소를 인자로 준다.

    .venv\\Scripts\\python.exe -m server.smoke_test https://<렌더주소>.onrender.com
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("APP_PASSWORD", "test1234")
os.environ.setdefault("SESSION_SECRET", "smoke-test-secret")
# 실제 호출은 하지 않는다. 설정이 채워졌는지만 보게 하는 자리값.
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-smoke-test-not-a-real-key")

results: list[tuple[bool, str]] = []


def check(condition: bool, label: str) -> None:
    results.append((bool(condition), label))
    print(f"{'통과' if condition else '실패'}  {label}")


def run(client, password: str) -> None:
    health = client.get("/api/health")
    check(health.status_code == 200, "서버 상태 확인이 응답한다")

    check(
        client.get("/api/config").status_code == 401,
        "토큰 없이 기준정보를 부르면 막힌다",
    )

    wrong = client.post("/api/auth", json={"password": "틀린비밀번호"})
    check(wrong.status_code == 401, "틀린 비밀번호는 거부된다")
    check(
        "message" in wrong.json() and not any(c.isascii() and c.isalpha() for c in wrong.json()["message"]),
        "거부 안내에 영문 기술 용어가 없다",
    )

    ok = client.post("/api/auth", json={"password": password})
    check(ok.status_code == 200, "맞는 비밀번호로 토큰이 발급된다")
    if ok.status_code != 200:
        return

    token = ok.json()["token"]
    config = client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
    check(config.status_code == 200, "토큰으로 기준정보를 받아온다")
    if config.status_code != 200:
        return

    data = config.json()
    counts = data.get("counts", {})
    check(counts.get("branches") == 24, f"지점 24개가 내려온다 (실제 {counts.get('branches')}개)")
    check(counts.get("procedure_categories") == 10, f"시술 카테고리 10개가 내려온다 (실제 {counts.get('procedure_categories')}개)")
    check(counts.get("procedures") == 237, f"시술 237개가 내려온다 (실제 {counts.get('procedures')}개)")
    check(len(data.get("personas", [])) == 6, "페르소나 6종이 내려온다")
    check(len(data.get("audiences", [])) == 6, "독자 타겟 6종이 내려온다")
    check(len(data.get("tones", [])) == 4, "톤 4종이 내려온다")
    check(len(data.get("platforms", [])) == 4, "플랫폼 4종이 내려온다")
    check(len(data.get("lengths", [])) == 3, "분량 3종이 내려온다")

    check(
        client.get("/api/config", headers={"Authorization": "Bearer eyJleHAiOjk5OTk5OTk5OTl9.fakesignature"}).status_code == 401,
        "위조한 토큰은 거부된다",
    )

    body = config.text
    check(
        "APP_PASSWORD" not in body and "SESSION_SECRET" not in body and "sk-ant" not in body,
        "응답에 비밀 값이 섞여 있지 않다",
    )

    check_generation_guards(client, token, data)
    check_rate_limit(client, token)
    check_cors_on_error()


class _FakeReq:
    """CORS 헤더 계산만 확인하기 위한 최소 요청 흉내."""

    def __init__(self, origin: str) -> None:
        self.headers = {"origin": origin} if origin else {}


def check_cors_on_error() -> None:
    """H2 — 처리 못 한 오류(500) 응답에도 CORS 헤더가 붙는지 본다.

    이게 빠지면 브라우저가 오류 응답을 가로막아, 실제로는 서버 오류인데
    화면에는 '연결 실패'로 잘못 보인다.
    """
    from . import main

    allowed = main._cors_headers(_FakeReq("http://localhost:8000"))
    check(
        allowed.get("Access-Control-Allow-Origin") == "http://localhost:8000",
        "허용된 곳에서 온 오류 응답에는 CORS 헤더가 붙는다",
    )

    denied = main._cors_headers(_FakeReq("https://evil.example"))
    check(
        "Access-Control-Allow-Origin" not in denied,
        "허용하지 않은 곳에는 CORS 헤더를 주지 않는다",
    )


def check_rate_limit(client, token: str) -> None:
    """H1 — 생성 호출이 한도를 넘으면 429로 막는지 본다 (비용 방어)."""
    from . import security, settings

    headers = {"Authorization": f"Bearer {token}"}

    security._generations.clear()
    original = settings.GEN_MAX_PER_WINDOW
    settings.GEN_MAX_PER_WINDOW = 3
    try:
        codes = [
            client.post("/api/keywords", json={"procedure": "antiaging-032"}, headers=headers).status_code
            for _ in range(6)
        ]
    finally:
        settings.GEN_MAX_PER_WINDOW = original
        security._generations.clear()

    # 한도 안(앞 3번)은 통과해 생성 단계로 넘어가고(키가 없으면 502), 넘으면 429로 막힌다.
    check(codes[0] != 429, "한도 안에서는 생성 호출이 통과한다")
    check(429 in codes, f"한도를 넘으면 429로 막는다 (실제 코드들: {codes})")


def check_generation_guards(client, token: str, config: dict) -> None:
    """3단계 — 글 목적(모드) 강제가 실제로 동작하는지 본다 (SPEC §5.6).

    Claude API 를 실제로 부르지 않고 확인할 수 있는 것만 검사한다.
    실제 호출은 키가 있어야 하므로 사람이 화면에서 확인한다.
    """
    headers = {"Authorization": f"Bearer {token}"}

    check(
        client.post("/api/keywords", json={"procedure": "antiaging-032"}).status_code == 401,
        "토큰 없이 키워드를 요청하면 막힌다",
    )

    # 없는 시술 id 는 생성 단계로 넘어가기 전에 걸러진다.
    bad = client.post("/api/keywords", json={"procedure": "존재하지-않는-시술"}, headers=headers)
    check(bad.status_code == 400, "없는 시술로 요청하면 생성 전에 걸러진다")

    # 정보성 모드에서 후기형 페르소나는 서버가 막는다 (화면에서 숨기는 것과 별개).
    blocked = client.post(
        "/api/keywords",
        json={"mode": "information", "procedure": "antiaging-032", "persona": "review"},
        headers=headers,
    )
    check(blocked.status_code == 400, "정보성 모드에서 후기형 페르소나는 서버가 막는다")

    # 홍보성에서는 같은 조합이 통과해야 한다(400 이 아니면 통과 — 키가 없으면 502 가 정상).
    allowed = client.post(
        "/api/keywords",
        json={"mode": "promotion", "procedure": "antiaging-032", "persona": "review"},
        headers=headers,
    )
    check(allowed.status_code != 400, "홍보성 모드에서는 후기형 페르소나가 허용된다")

    check_prompt_guards(config)
    check_compliance(client, token)


def check_compliance(client, token: str) -> None:
    """4단계 — 의료법 검사가 실제로 잡고 막는지 본다 (SPEC §6).

    Claude 를 부르지 않고 확인할 수 있게 quick(규칙 검사만) 으로 돌린다.
    """
    from . import compliance

    headers = {"Authorization": f"Bearer {token}"}

    check(
        client.post("/api/compliance", json={"text": "아무 글"}).status_code == 401,
        "토큰 없이 검사를 요청하면 막힌다",
    )
    check(
        client.post("/api/compliance", json={"text": "  "}, headers=headers).status_code == 400,
        "빈 글로 검사를 요청하면 걸러진다",
    )

    bad = "국내 유일의 최고의 장비로 부작용 없는 시술. 100% 만족. 8월 30% 할인 이벤트, 시술비 150,000원. 지금 예약하세요."

    res = client.post(
        "/api/compliance",
        json={"text": bad, "mode": "information", "quick": True},
        headers=headers,
    )
    check(res.status_code == 200, "검사가 응답한다")
    if res.status_code != 200:
        return

    info = res.json()
    check(info["blocked"] is True, "위험 표현이 있으면 복사를 막는다고 알린다")
    check(info["counts"]["danger"] >= 8, f"위험 표현을 충분히 잡는다 (실제 {info['counts']['danger']}건)")

    phrases = [i["phrase"] for i in info["issues"]]
    for expected in ["국내 유일", "부작용 없는", "100%", "할인", "전후사진" if "전후사진" in bad else "지금 예약"]:
        check(expected in phrases, f"'{expected}' 를 잡아낸다")

    check(
        all(i["phrase"] in bad for i in info["issues"]),
        "지적한 문구는 모두 본문에 실제로 있는 그대로다",
    )

    # 같은 글이라도 모드에 따라 등급이 달라야 한다 (§6.3)
    promo = client.post(
        "/api/compliance",
        json={"text": bad, "mode": "promotion", "quick": True},
        headers=headers,
    ).json()
    check(
        promo["counts"]["danger"] < info["counts"]["danger"],
        f"홍보성은 정보성보다 위험 판정이 적다 ({promo['counts']['danger']} < {info['counts']['danger']})",
    )

    def level_of(result, phrase):
        return next((i["level"] for i in result["issues"] if i["phrase"] == phrase), None)

    check(level_of(info, "할인") == "danger", "정보성에서 '할인' 은 위험")
    check(level_of(promo, "할인") == "warn", "홍보성에서 '할인' 은 주의")

    # 깨끗한 글은 아무것도 잡히면 안 된다 (오탐 방지)
    clean = (
        "레이저 시술 후 회복 기간은 피부 상태에 따라 다를 수 있습니다. "
        "붉은기는 보통 2~3일이면 가라앉고 각질은 일주일 정도 지속됩니다. "
        "개인차가 있으니 조급해하지 않으셔도 됩니다."
    )
    ok = compliance.check(clean, "information", use_llm=False)
    check(ok["counts"]["danger"] == 0, f"정상적인 글은 위험으로 잡지 않는다 (실제 {ok['counts']['danger']}건)")
    check(ok["blocked"] is False, "정상적인 글은 복사를 막지 않는다")


def check_prompt_guards(config: dict) -> None:
    """프롬프트에 금지 요소가 실제로 빠지는지 문자열 단위로 확인한다."""
    from . import prompts

    payload = {
        "branch": "gangnam",
        "procedure": "antiaging-032",
        "persona": "doctor",
        "audience": config["audiences"][0]["id"],
        "tone": config["tones"][0]["id"],
        "platform": "naver",
        "length": "medium",
        "cta": "8월 한정 30% 할인, 지금 예약하세요",
        "reference": "",
        "persona_custom": "",
    }
    ctx = prompts.build_context(payload, config)
    check(ctx["procedure"] is not None, "시그니처 시술을 id 로 찾아낸다")

    info_brief = prompts.build_brief(payload, ctx, prompts.MODE_INFORMATION)

    # 정보성: cta 를 비운 뒤 프롬프트를 만든다(라우터가 하는 일과 동일).
    info_draft = prompts.draft_prompt(
        brief=info_brief, title="테스트 제목", keywords=["테스트"],
        target_chars=2000, platform_id="naver",
        mode=prompts.MODE_INFORMATION, cta="",
    )
    check("30% 할인" not in info_draft, "정보성 본문 프롬프트에 할인 문구가 들어가지 않는다")
    check("예약" in info_draft and "절대 넣지 않는다" in info_draft, "정보성 본문 프롬프트가 예약 유도를 금지한다")

    promo_draft = prompts.draft_prompt(
        brief=info_brief, title="테스트 제목", keywords=["테스트"],
        target_chars=2000, platform_id="naver",
        mode=prompts.MODE_PROMOTION, cta=payload["cta"],
    )
    check("30% 할인" in promo_draft, "홍보성 본문 프롬프트에는 안내 문구가 들어간다")

    info_system = prompts.system_prompt(prompts.MODE_INFORMATION)
    promo_system = prompts.system_prompt(prompts.MODE_PROMOTION)
    check("가격, 비용, 할인" in info_system, "정보성 시스템 규칙이 가격·할인을 차단한다")
    check("100%" in info_system and "100%" in promo_system, "두 모드 모두 효과 단정을 금지한다")
    check(info_system != promo_system, "모드에 따라 시스템 규칙이 달라진다")


def main() -> int:
    import httpx

    base_url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else ""

    if base_url:
        password = os.environ.get("SMOKE_PASSWORD") or input("공통 비밀번호: ")
        print(f"\n배포된 서버를 확인합니다: {base_url}\n")
        with httpx.Client(base_url=base_url, timeout=60.0) as client:
            run(client, password)
    else:
        from fastapi.testclient import TestClient

        from .main import app

        print("\n로컬에서 확인합니다.\n")
        with TestClient(app) as client:
            run(client, os.environ["APP_PASSWORD"])

    failed = [label for ok, label in results if not ok]
    print()
    if failed:
        print(f"{len(failed)}개 항목이 실패했습니다.")
        return 1
    print(f"{len(results)}개 항목 모두 통과했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
