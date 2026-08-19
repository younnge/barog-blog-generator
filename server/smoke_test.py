"""1~3단계 점검 스크립트.

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
