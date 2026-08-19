# 인수인계 요약

> 갱신 2026-08-19 · 상태: **`SPEC.md` §15 1~7단계 완료** · 남은 것: **8단계 시범 사용** (사람이 하는 일)
>
> 화면: `https://younnge.github.io/barog-blog-generator/`
> 서버: `https://barog-blog-generator-api.onrender.com` (무료 플랜)
> 저장소: `younnge/barog-blog-generator` (Public)
> 마케터에게 줄 문서: **`사용안내.md`**

---

## 1. 지금 되는 것

링크 접속 → 비밀번호 → 버튼 선택 → 키워드 고르기 → 제목 고르기 → 본문 생성 →
의료법 검사 → 문구 교체 → 플랫폼별 복사 → 이력 저장까지 **처음부터 끝까지 동작한다.**

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | 백엔드 스켈레톤 + 인증 + `/api/config` | ✅ |
| 2 | 프론트 정적 화면 + 기준정보 렌더링 | ✅ |
| 3 | 키워드 → 제목 → 본문 파이프라인 + 글 목적(모드) | ✅ |
| 4 | 의료법 검사 + 복사 차단 | ✅ |
| 5 | 플랫폼별 포맷 변환 | ✅ |
| 6 | 이력 저장·조회 (브라우저 저장) | ✅ |
| 7 | 디자인 마감 · 접근성 | ✅ |
| **8** | **마케터 1명 시범 → 피드백 → 전체 오픈** | **남음** |

---

## 2. 구조

```
[GitHub Pages]                          [Render]
 index.html        ── HTTPS/JSON ──▶     FastAPI
 assets/app.js                            ├─ /api/auth      비밀번호 검증, 토큰 30일
 assets/styles.css                        ├─ /api/config    기준정보
 config/*.json                            ├─ /api/keywords  Haiku
 (정적, 무료)                              ├─ /api/titles    Haiku
                                          ├─ /api/draft     Sonnet
                                          ├─ /api/draft/section  Sonnet
                                          └─ /api/compliance     규칙 + Haiku
                                                    │
                                              [Claude API]
```

**이력은 서버에 없다.** 각자 브라우저(`localStorage`)에만 쌓인다 (§10.2).

### 파일

| 파일 | 역할 |
|---|---|
| `server/settings.py` | 환경변수. 비밀·키는 전부 여기서만 읽는다 |
| `server/security.py` | 비밀번호 해시 비교, 토큰 서명, 시도 제한 |
| `server/config_store.py` | `config/*.json` 로딩 (파일 바뀌면 재시작 없이 반영) |
| `server/prompts.py` | 모드별 프롬프트 조립 + 응답 스키마 |
| `server/llm.py` | Claude 호출. 모든 실패를 한국어 문장으로 변환 |
| `server/compliance.py` | 1차 규칙 매칭 + 2차 문맥 판정 |
| `server/routes/` | `auth` `config` `generate` `check` |
| `server/smoke_test.py` | 점검 43항목 |
| `config/compliance.json` | 금지어 사전 19규칙 / 105표현 |
| `tools/bump.py` | 배포 전 화면 파일 버전 올리기 |

---

## 3. 확정된 결정

### 글 목적 (모드) — 이 프로젝트의 중심 개념
`SPEC.md` §5.6. 정보성 / 홍보성 두 가지.

의료광고 규정이 잡는 **금지 5요소**(효과보장·최상급 / 가격·이벤트 / 전후사진 / 체험담 / 예약유도)를
**정보성 모드에서는 아예 만들지 않는다.** 검사로 걷어내는 게 아니라 생성 단계에서 막는다.

- 정보성 → `cta` 입력란이 사라지고, 서버는 `cta` 값이 와도 **무시**한다
- 정보성 → 후기형 페르소나를 서버가 **400으로 막는다**
- 화면에서 숨기는 건 편의일 뿐, **차단은 서버가 한다** (우회 경로를 만들지 않는다)

### 모델 (SPEC §8.4)
키워드·제목·의료법 2차 검사 = `claude-haiku-4-5`
본문·문단 재생성 = `claude-sonnet-5`
환경변수 `MODEL_FAST` / `MODEL_MAIN` 으로 교체 가능.

### 이력 저장 (2026-08-19 확정)
**외부 저장소 없음.** 각자 브라우저에만. 팀 공유 불필요하다는 판단.
`historyStore` 한 곳에 모아뒀으니, 나중에 필요하면 그 안쪽만 서버 호출로 바꾸면 된다.

### 다국어 (2026-08-19 확정)
**Phase 1 이후로 미룸.** 근거: 법무·심의 검토 결과 미도착 / 언어별 금지어 사전의 근거 없음 /
중국어(샤오홍슈)는 별도 파이프라인 / 현지인 검수자 미계약.
단 `lang` 파라미터와 이력 필드 자리는 **이미 만들어 뒀다**.

---

## 4. 운영에 필요한 것

### 환경변수 (Render 대시보드)
| 키 | 설명 |
|---|---|
| `APP_PASSWORD` | 팀 공통 비밀번호 |
| `SESSION_SECRET` | 토큰 서명키. 바꾸면 전원 재로그인 |
| `ANTHROPIC_API_KEY` | Claude 키. **없으면 로그인부터 막힌다** |
| `ALLOWED_ORIGINS` | `https://younnge.github.io` |

로컬 테스트는 `server/.env` (저장소에 안 올라감). 견본은 `server/.env.example`.

### 배포
- 화면: `main` 에 푸시하면 GitHub Pages 자동 반영
- 서버: `main` 에 푸시하면 Render 자동 재배포
- **푸시 전에 `python tools/bump.py` 를 돌린다.** 안 그러면 마케터 브라우저가 예전 화면을 계속 쓴다

### 점검
```
.venv\Scripts\python.exe -m server.smoke_test
```
43항목. 배포된 서버를 볼 때는 주소를 인자로 준다.

### 로컬에서 띄우기
```powershell
# 서버
cd "...\barog-blog-generator"; .venv\Scripts\python.exe -m uvicorn server.main:app --port 8001

# 화면 (다른 창)
cd "...\barog-blog-generator"; python -m http.server 8000
```
브라우저에서 `http://localhost:8000`

---

## 5. 남은 일 — 8단계

### 개발 쪽
1. 마케터 1명에게 `사용안내.md` 와 링크를 주고 **혼자 글 한 편을 뽑게 한다**
2. 볼 것: 3분 안에 되는가 / 어디서 막히는가 / 어떤 문구가 안 통하는가
3. **네이버 스마트에디터에 실제로 붙여넣어** 줄바꿈이 깨지지 않는지 확인 (자동 검사로는 확인 못 하는 부분)
4. 피드백 반영 후 전체 오픈

### 개발과 별개로 (병행)
| 항목 | 왜 |
|---|---|
| **의료광고 심의기관 질의 또는 법무 검토** | `config/compliance.json` 은 `SPEC.md` §6.3 을 근거로 만든 것이지 법률 자문이 아니다. 검토 결과가 나오면 이 파일을 갱신해야 한다 |
| 파일럿 시술 카테고리 1개 선정 | `바로그 코어 레이저`(`antiaging-032`)와 직결되면서 경쟁 낮은 영역 |
| 원장님 격주 30분 인터뷰 일정 고정 | 입력 화면 `참고자료` 칸의 재료. 이게 없으면 결과물이 일반적인 AI 글과 구분되지 않는다 |

---

## 6. 다음 Phase (아직 손대지 않음)

| Phase | 범위 |
|---|---|
| 2 | 이미지 생성 — 썸네일 1장 + 본문 삽입 3~5장 |
| 3 | 자동 발행 — 워드프레스만. **네이버는 공식 API 없어 제외 권장** (계정 제재 리스크) |
| 1.5 | 관리자 탭 — `config/*.json` 을 화면에서 수정 |
| 후속 | 다국어 (영 → 일 → 중 → 태) |

Phase 1 이 안정화되기 전까지 섞지 않는다.

---

## 7. 작업할 때 지킬 것

- `CLAUDE.md` 절대 규칙 7개를 먼저 읽는다
- `SPEC.md` 와 충돌하면 `SPEC.md` 가 우선
- 미확정 항목은 임의로 정하지 말고 물어본다
- 각 단계가 끝나면 멈추고 확인받는다
- 주석·커밋 메시지는 한국어
