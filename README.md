# 바로그 블로그 글 생성기

피부과 네트워크(바로그의원) 인하우스 마케팅팀이 쓰는 블로그 글 초안 생성 사내 도구.

- 요구사항: [SPEC.md](SPEC.md)
- 작업 규칙: [CLAUDE.md](CLAUDE.md)
- 진행 상황: [HANDOFF.md](HANDOFF.md)

## 지금 상태

**Phase 1 / 1단계 완료** — 백엔드 뼈대 + 로그인 + 기준정보 API.
화면(2단계)과 글 생성(3단계)은 아직 없다.

| 주소 | 하는 일 | 로그인 필요 |
|---|---|---|
| `GET /api/health` | 서버가 살아 있는지 확인 (무료 플랜 깨우기용) | 아니오 |
| `POST /api/auth` | 공통 비밀번호 확인 → 30일 토큰 발급 | 아니오 |
| `GET /api/config` | 지점·시술·페르소나·독자타겟·톤·플랫폼·분량 전체 | 예 |

## 배포 구조

```
GitHub Pages (화면, 2단계에서 추가)  ──HTTPS──▶  Render (서버, 지금 이 코드)
```

- Anthropic API 키와 공통 비밀번호는 **Render 환경변수에만** 존재한다. 저장소에 넣지 않는다.
- 서버는 `ALLOWED_ORIGINS`에 적힌 주소에서 오는 호출만 받는다.

## Render 설정 (관리자용)

1. [render.com](https://render.com) 로그인 → **New +** → **Blueprint**
2. 이 저장소(`barog-blog-generator`)를 선택 → `render.yaml`을 자동으로 읽는다
3. 환경변수 두 개를 입력하라고 나온다:

   | 이름 | 넣을 값 |
   |---|---|
   | `APP_PASSWORD` | 팀이 함께 쓸 공통 비밀번호 |
   | `SESSION_SECRET` | 아무 긴 랜덤 문자열 (아래 명령으로 생성) |

   랜덤 문자열 생성:
   ```
   py -3 -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
4. **Apply** → 첫 배포에 3~5분
5. 배포된 주소로 확인:
   ```
   https://<서비스주소>.onrender.com/api/health
   ```
   `{"status":"ok","ready":true}` 가 보이면 성공이다. `ready`가 `false`면 환경변수가 덜 들어간 것이다.

### 비밀번호를 바꿀 때
Render 대시보드 → Environment → `APP_PASSWORD` 수정 → 저장(자동 재배포).
이미 로그인한 사람은 그대로 유지된다. **전원 재로그인**을 시키려면 `SESSION_SECRET`도 함께 바꾼다.

### 무료 플랜 참고
15분 동안 아무도 안 쓰면 서버가 잠든다. 다음 사람이 눌렀을 때 최대 50초 기다릴 수 있다.
2단계 화면에서 접속하자마자 `/api/health`를 호출해 미리 깨우고 "서버 깨우는 중" 안내를 띄운다.
대기가 거슬리면 Render 대시보드에서 Starter($7/월)로 올리면 바로 해결된다.

## 기준정보 수정 (지점·시술 추가/삭제)

버튼은 코드가 아니라 `config/*.json`을 읽어 그려진다. **JSON만 고치고 push하면 끝이다.**

| 파일 | 내용 |
|---|---|
| `config/branches.json` | 지점 24개 |
| `config/procedures.json` | 시술 10개 카테고리 / 237개 |
| `config/personas.json` | 글쓴이 시점 6종 |
| `config/audiences.json` | 독자 타겟 6종 |
| `config/tones.json` | 톤 4종 |

- 지점 추가: `{ "id": "새주소", "name": "○○점", "active": true, "note": "" }` 한 줄 추가
- 지점 삭제: **항목을 지우지 말고** `"active": false`로 바꾼다. 지워버리면 과거 이력의 지점 이름이 깨진다.
- 시술도 같은 방식이다.

## 로컬에서 확인하기 (개발용)

```
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r server/requirements.txt
copy server\.env.example server\.env
.\.venv\Scripts\python.exe -m uvicorn server.main:app --reload --port 8000
```

`server/.env`의 비밀번호는 로컬 테스트용이며 저장소에 올라가지 않는다.

### 점검 스크립트

```
.\.venv\Scripts\python.exe -m pip install httpx
.\.venv\Scripts\python.exe -m server.smoke_test
```

로그인·차단·기준정보 개수를 한 번에 확인한다. 배포된 서버를 확인하려면 주소를 뒤에 붙인다:

```
.\.venv\Scripts\python.exe -m server.smoke_test https://<서비스주소>.onrender.com
```

## 파일 구조

```
config/            기준정보 JSON (화면 버튼의 원본)
server/
  main.py          앱 진입점, CORS, 에러 문구
  settings.py      환경변수
  security.py      비밀번호 비교, 토큰 발급·검증, 시도 제한
  config_store.py  config/*.json 읽기
  routes/          /api/auth, /api/config
  smoke_test.py    점검 스크립트
render.yaml        Render 배포 설정
```
