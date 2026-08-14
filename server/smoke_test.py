"""1단계 점검 스크립트.

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
    check("APP_PASSWORD" not in body and "SESSION_SECRET" not in body, "응답에 비밀 값이 섞여 있지 않다")


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
