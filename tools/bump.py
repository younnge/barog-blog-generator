"""화면 파일 버전 올리기.

브라우저는 한 번 받은 assets/app.js 를 한동안 다시 받지 않는다.
그래서 코드를 고쳐도 예전 화면이 그대로 보이는 일이 생긴다.
주소 뒤 ?v= 숫자를 올리면 브라우저가 새 파일로 인식해 다시 받는다.

배포(푸시) 전에 한 번 실행한다.

    python tools/bump.py
"""

from __future__ import annotations

import io
import re
from pathlib import Path

INDEX = Path(__file__).resolve().parent.parent / "index.html"


def main() -> int:
    text = io.open(INDEX, encoding="utf-8").read()

    versions = [int(m) for m in re.findall(r"assets/(?:app\.js|styles\.css)\?v=(\d+)", text)]
    if not versions:
        print("버전 표시를 찾지 못했습니다. index.html 의 assets 링크를 확인해 주세요.")
        return 1

    new = max(versions) + 1
    text = re.sub(r"(assets/(?:app\.js|styles\.css))\?v=\d+", rf"\1?v={new}", text)
    io.open(INDEX, "w", encoding="utf-8", newline="").write(text)

    print(f"화면 파일 버전을 {max(versions)} -> {new} 로 올렸습니다.")
    print("이제 커밋하고 푸시하면 모두가 새 화면을 받습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
