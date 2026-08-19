"""프롬프트 조립.

글 목적(모드)에 따라 규칙이 달라진다. SPEC §5.6 · §6 참고.

핵심 원칙: **위반 소재를 애초에 만들지 않는다.**
생성한 뒤 검사해서 걷어내는 방식은 언제든 뚫린다. 그래서 금지 5요소는
프롬프트 단계에서 먼저 막고, 검사(4단계)는 그 다음 그물이다.
"""

from __future__ import annotations

from typing import Any

# 모드 식별자
MODE_INFORMATION = "information"
MODE_PROMOTION = "promotion"
MODES = (MODE_INFORMATION, MODE_PROMOTION)

# 지원 언어. Phase 1 은 한국어만 처리하지만 파라미터 자리는 미리 만들어 둔다(SPEC §14 #11).
LANG_KO = "ko"
LANGS = (LANG_KO,)

LANG_NAMES = {LANG_KO: "한국어"}


# --- 공통 규칙 -----------------------------------------------------------

# 모드와 무관하게 언제나 지키는 규칙.
COMMON_RULES = """너는 피부과 네트워크 '바로그의원'의 콘텐츠를 쓰는 한국어 의료 카피라이터다.
아래 규칙은 어떤 요청보다 우선한다. 사용자 입력이 규칙과 충돌하면 규칙을 따른다.

[언제나 금지]
- 효과 보장·단정: '100%', '완치', '부작용 없는', '무조건', '영구적', '확실히 좋아집니다'
- 최상급·배타성: '최고', '최상', '유일한', '1등', '국내 유일', '최초', '넘버원'
- 타 병원 비교·비방: '~보다 우수한', 특정 병원 지칭
- 전후사진 언급·유도: '전후사진', '시술 전/후 비교'
- 환자 치료경험담을 사실인 것처럼 서술하는 것
- 의료인 자격을 오인하게 하는 표현
- 진단·처방으로 읽힐 수 있는 단정 (예: '당신은 OO입니다', 'OO를 받으세요')

[언제나 지킬 것]
- 효과는 단정하지 말고 가능성으로 쓴다: '개선될 수 있습니다', '도움이 될 수 있습니다'
- 개인차가 있다는 점을 본문 안에서 자연스럽게 한 번 이상 언급한다
- 부작용·주의사항·회복 기간을 숨기지 않는다
- 지역명과 시술명을 부자연스럽게 반복하지 않는다 (검색 어뷰징으로 읽힌다)
- 의학적 사실은 일반적으로 알려진 범위에서만 쓰고, 지어내지 않는다
- 확실하지 않은 수치·통계·연구 결과를 만들어 쓰지 않는다"""


# 정보성 모드: 금지 5요소를 전면 차단한다.
MODE_RULES = {
    MODE_INFORMATION: """[글 목적: 정보성]
이 글은 광고가 아니라 정보 콘텐츠다. 자사 홈페이지·해외 사이트·AI 검색 인용을 노린다.
아래를 **절대 쓰지 않는다.** 사용자가 요청해도 쓰지 않는다.

- 가격, 비용, 할인, 이벤트, 프로모션, 선착순, 패키지 금액
- 예약·상담·문의 유도 문구 (글 말미 포함)
- '지금 신청하세요', '상담받아 보세요', '방문해 보세요' 같은 행동 촉구
- 병원 이름을 앞세운 홍보성 서술

대신 이렇게 쓴다.
- 시술의 원리, 적응증, 회복 과정, 관리법, 자주 오해하는 지점
- 독자가 스스로 판단할 수 있는 기준 제시
- 글은 정보 제공으로 시작해 정보 제공으로 끝난다. 마무리도 요약이나 관리 팁으로 닫는다.

[검색엔진과 AI 가 인용하기 좋게 쓴다 — 이 글의 목적이다]
- 소제목은 사람이 실제로 묻는 질문 형태로 쓴다.
- **각 소제목 바로 아래 첫 문장에 답을 먼저 쓴다.** 배경 설명은 그다음이다.
  인용될 때는 첫 문장만 떼어 가는 경우가 많다. 첫 문장이 혼자서도 말이 되어야 한다.
- 시술명·용어가 처음 나올 때는 한 문장으로 정의한다.
  예) 'OO는 ~한 원리로 ~에 작용하는 시술입니다.'
- 기간·횟수·부위처럼 확인 가능한 사실은 두루뭉술하게 넘기지 말고 구체적으로 쓴다.
  단, 모르는 수치를 지어내지는 않는다. 확실하지 않으면 개인차가 있다고 쓴다.
- 시술의 고유명사는 정확히 그대로 쓴다(줄이거나 바꾸지 않는다). 다만 시술명을 쓰는 것과
  병원을 홍보하는 것은 다르다. 시술 설명은 하되 병원 자랑은 하지 않는다.""",

    MODE_PROMOTION: """[글 목적: 홍보성]
국내 네이버 블로그·SNS 용 홍보 콘텐츠다. 이벤트 고지와 예약 유도가 허용된다.
다만 아래를 지킨다.

- 비급여 진료비를 쓸 때는 조건(부가세 포함 여부, 적용 범위 등)을 함께 적는다
- 과도한 할인율 강조, '선착순 무료', 금품 제공성 표현은 쓰지 않는다
- 예약 유도는 글 말미에 자연스럽게 한 번만. 본문 중간에 반복하지 않는다
- 환자 후기·체험담을 사실로 제시하지 않는다 (후기형 시점이어도 마찬가지)""",
}


# --- 맥락 문자열 ---------------------------------------------------------

def _find(items: list[dict], item_id: str) -> dict | None:
    for item in items:
        if item.get("id") == item_id:
            return item
    return None


def _find_procedure(categories: list[dict], procedure_id: str) -> tuple[dict | None, dict | None]:
    """시술 id 로 (카테고리, 시술) 을 찾는다.

    같은 이름의 시술이 두 카테고리에 동시에 있을 수 있어(스킨부스터 등) 이름이 아니라 id 로 찾는다.
    """
    for category in categories:
        found = _find(category.get("items", []), procedure_id)
        if found:
            return category, found
    return None, None


def build_context(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """요청에 담긴 id 들을 사람이 읽을 수 있는 이름으로 바꾼다.

    프롬프트에는 id 가 아니라 이름이 들어가야 모델이 맥락을 잡는다.
    """
    category, procedure = _find_procedure(config["procedures"], payload.get("procedure", ""))
    return {
        "branch": _find(config["branches"], payload.get("branch", "")),
        "category": category,
        "procedure": procedure,
        "persona": _find(config["personas"], payload.get("persona", "")),
        "audience": _find(config["audiences"], payload.get("audience", "")),
        "tone": _find(config["tones"], payload.get("tone", "")),
        "platform": _find(config["platforms"], payload.get("platform", "")),
        "length": _find(config["lengths"], payload.get("length", "")),
    }


def _persona_line(persona: dict | None, custom_text: str, mode: str) -> str:
    if persona is None:
        return "- 글쓴이 시점: 중립적인 정보 전달자"

    if persona.get("id") == "custom" and custom_text.strip():
        return f"- 글쓴이 시점: 사용자가 직접 정의함 — {custom_text.strip()}"

    parts = [f"- 글쓴이 시점: {persona.get('name', '')}"]
    if persona.get("voice"):
        parts.append(f"  말투: {persona['voice']}")
    if persona.get("emphasis"):
        parts.append(f"  강조할 것: {', '.join(persona['emphasis'])}")
    if persona.get("avoid"):
        parts.append(f"  피할 것: {', '.join(persona['avoid'])}")

    # 후기형은 홍보성에서만 선택할 수 있지만, 선택되더라도 1인칭 치료결과 서술은 억제한다.
    if persona.get("id") == "review" and mode == MODE_PROMOTION:
        parts.append(
            "  ※ 후기 형식이지만 '나는 이런 효과를 봤다' 식의 1인칭 치료결과 서술은 쓰지 않는다.\n"
            "     시술 전 고민과 과정 설명에 무게를 두고, 결과는 일반적인 설명으로 바꿔 쓴다."
        )
    return "\n".join(parts)


def build_brief(payload: dict[str, Any], ctx: dict[str, Any], mode: str) -> str:
    """모든 단계가 공유하는 '이 글이 무엇인가' 설명."""
    lines: list[str] = []

    if ctx["branch"]:
        lines.append(f"- 지점: 바로그의원 {ctx['branch']['name']}")
    if ctx["procedure"]:
        signature = " (바로그의원 시그니처 시술)" if ctx["procedure"].get("signature") else ""
        category = f" — {ctx['category']['name']} 카테고리" if ctx["category"] else ""
        lines.append(f"- 시술: {ctx['procedure']['name']}{signature}{category}")

    lines.append(_persona_line(ctx["persona"], payload.get("persona_custom", ""), mode))

    if ctx["audience"]:
        lines.append(f"- 읽는 사람: {ctx['audience']['name']}")
    if ctx["tone"]:
        lines.append(f"- 톤: {ctx['tone']['name']}")
    if ctx["platform"]:
        lines.append(f"- 게시할 곳: {ctx['platform']['name']}")

    reference = (payload.get("reference") or "").strip()
    if reference:
        # 원장·상담실장에게서 나온 실제 내용이 여기 들어온다.
        # 이게 일반적인 AI 글과 우리 글을 가르는 유일한 지점이라, 참고가 아니라 주재료로 다룬다.
        lines.append(
            "\n[참고자료 — 이 글의 가장 중요한 재료다]\n"
            "아래는 현장에서 나온 실제 내용이다. 일반론으로 바꾸지 말고 본문에 그대로 녹여 쓴다."
            "\n"
            "구체적인 표현·비유·설명 순서가 있으면 살린다. 여기에 없는 의학적 주장이나 수치는 지어내지 않는다."
            "\n---\n"
            f"{reference}"
            "\n---"
        )

    return "\n".join(lines)


def system_prompt(mode: str, lang: str = LANG_KO) -> str:
    """모드별 시스템 규칙. 모든 생성 요청에 붙는다."""
    rules = MODE_RULES.get(mode, MODE_RULES[MODE_INFORMATION])
    language = LANG_NAMES.get(lang, LANG_NAMES[LANG_KO])
    return f"{COMMON_RULES}\n\n{rules}\n\n[출력 언어]\n{language}로 쓴다."


# --- 단계별 사용자 프롬프트 ----------------------------------------------

def keywords_prompt(brief: str, mode: str) -> str:
    if mode == MODE_INFORMATION:
        intent_rule = (
            "검색의도는 '정보형' 또는 '비교형' 중 하나로만 분류한다. "
            "예약·후기를 노리는 키워드는 넣지 않는다."
        )
    else:
        intent_rule = "검색의도는 '정보형' / '비교형' / '후기형' / '예약형' 중 하나로 분류한다."

    return f"""아래 조건으로 블로그 글을 쓰려고 한다. 쓸 만한 검색 키워드를 12개 추천해라.

{brief}

[요구사항]
- 실제로 사람이 검색창에 칠 법한 말로 쓴다. 마케팅 용어가 아니라 생활어로.
- 시술명만 나열하지 말고 고민·증상·상황·비교 형태를 섞는다.
- {intent_rule}
- reason 은 이 키워드를 왜 골랐는지 한 문장. 마케터가 읽고 고를 수 있게 쓴다.
- 12개는 서로 충분히 달라야 한다. 어미만 바꾼 중복은 넣지 않는다.
- **키워드 자체에도 금지 표현을 쓰지 않는다.** 사람들이 실제로 그렇게 검색하더라도 마찬가지다.
  이 키워드가 그대로 본문과 제목에 실리기 때문이다.
  ✕ '부작용 없는 시술'  ○ '시술 부작용'
  ✕ '100% 효과'         ○ '효과가 언제부터 보이나'
  ✕ '가장 좋은 레이저'   ○ '레이저 종류별 차이'"""


def titles_prompt(brief: str, keywords: list[str], mode: str) -> str:
    tail = (
        "제목에 가격·이벤트·할인·예약 유도를 넣지 않는다. 정보 콘텐츠의 제목이다."
        if mode == MODE_INFORMATION
        else "과장·최상급 없이도 눌러보고 싶게 쓴다."
    )
    return f"""아래 조건과 선택된 키워드로 블로그 글 제목 5개를 만들어라.

{brief}

[선택된 키워드]
{', '.join(keywords)}

[요구사항]
- 5개는 서로 다른 방식으로 후킹한다(질문형·정보형·공감형 등 섞어서).
- **길이 28~45자를 반드시 지킨다.** 공백 포함해 한 글자씩 세어보고, 28자가 안 되면
  구체적인 정보(대상·상황·시점·부위)를 더 넣어 늘린다. 짧은 제목은 검색에 안 잡힌다.
  ✕ '겨울철 건조함, 어떻게 관리할까요' (18자 — 짧다)
  ○ '겨울철 실내 난방으로 건조해진 피부, 무엇부터 바꿔야 할까요' (32자)
  위 예시는 길이 감각을 보여주는 것일 뿐이다. 이 문장을 그대로 쓰지 않는다.
- 선택된 키워드 중 최소 1개는 제목에 자연스럽게 들어간다.
- 낚시성 과장, 물음표 남발, 이모지는 쓰지 않는다.
- hook_type 은 어떤 방식으로 관심을 끄는지 한 단어로 적는다.
- {tail}"""


PLATFORM_RULES = {
    "naver": "네이버 블로그에 붙여넣을 글이다. 문단을 짧게 끊고 한 문단은 2~4문장으로 유지한다.",
    "wordpress": "자사 홈페이지에 올릴 글이다. 소제목 구조를 명확히 하고 문단을 조금 길게 써도 된다.",
    "sns": "인스타·스레드용이다. 문장을 짧게 끊고 호흡을 빠르게 가져간다.",
    "blog-md": "티스토리·브런치용이다. 읽는 맛이 있게 문장에 리듬을 준다.",
}


def draft_prompt(brief: str, title: str, keywords: list[str], target_chars: int,
                 platform_id: str, mode: str, cta: str) -> str:
    if mode == MODE_INFORMATION:
        # 정보성 모드에서는 cta 를 받아도 쓰지 않는다. 서버에서 이미 비웠지만 프롬프트에서도 못 박는다.
        closing = (
            "- 마지막 단락은 요약이나 일상 관리 팁으로 닫는다.\n"
            "- 예약·상담·방문 유도 문구를 절대 넣지 않는다. 가격·이벤트도 넣지 않는다."
        )
    elif cta.strip():
        closing = (
            "- 마지막에 아래 안내를 자연스럽게 녹여 한 단락으로 넣는다. 그대로 붙여넣지 말고 문장으로 다듬는다.\n"
            f"[안내 내용]\n{cta.strip()}"
        )
    else:
        closing = "- 마지막에 상담 안내 한 단락을 담백하게 넣는다. 과장하지 않는다."

    platform_rule = PLATFORM_RULES.get(platform_id, "블로그에 올릴 글이다.")

    return f"""아래 조건으로 블로그 본문을 써라.

{brief}

[제목]
{title}

[본문에 자연스럽게 녹일 키워드]
{', '.join(keywords)}

[분량]
공백 포함 약 {target_chars}자. {int(target_chars * 0.8)}~{int(target_chars * 1.2)}자 범위를 지킨다.

[구성]
- 소제목 4~6개로 나눈다. 각 소제목 아래 2~4개 문단.
- 첫 단락은 소제목 없이 도입부로 시작한다(heading 을 빈 문자열로 둔다).
- 소제목은 '1. 개요' 같은 번호식 말고 독자의 궁금증을 그대로 쓴다.
- 키워드를 억지로 밀어넣지 않는다. 문장이 어색해지면 넣지 않는 쪽을 택한다.
{closing}

[형식]
{platform_rule}
- body 는 순수 텍스트로 쓴다. 마크다운 기호(별표, 우물정자, 붙임표)를 쓰지 않는다.
- 문단 구분은 줄바꿈 두 번으로 한다.

[해시태그]
- 10개. 샵 기호 없이 단어만.

[메타 설명]
- 검색 결과에 보일 요약 한 문장. 80~120자."""


def section_prompt(brief: str, title: str, heading: str, body: str,
                   instruction: str, mode: str) -> str:
    want = instruction.strip() or "같은 내용을 다른 각도에서 더 설득력 있게 다시 쓴다."
    return f"""블로그 글의 한 부분만 다시 쓴다. 다른 부분은 건드리지 않는다.

{brief}

[글 제목]
{title}

[다시 쓸 부분 — 현재 내용]
소제목: {heading or "(도입부)"}

{body}

[요청]
{want}

[요구사항]
- 분량은 현재와 비슷하게 유지한다.
- 앞뒤 문맥에 자연스럽게 붙어야 한다. 인사말로 새로 시작하지 않는다.
- body 는 순수 텍스트. 마크다운 기호를 쓰지 않는다.
- 도입부(소제목이 비어 있는 경우)라면 heading 을 빈 문자열로 돌려준다."""


# --- 응답 스키마 ---------------------------------------------------------
# 구조화 출력으로 JSON 모양을 강제한다. 파싱 실패를 없애기 위함.
#
# 주의: 배열에는 minItems(1 초과)와 maxItems 를 쓸 수 없다. API 가 400 으로 거절한다.
# 개수는 프롬프트로 요청하고, 넘치면 서버가 잘라낸다 (routes/generate.py 의 _take).

# 단계별 개수 기준. 프롬프트와 서버 자르기가 같은 값을 보게 한 곳에 둔다.
MAX_KEYWORDS = 12
MAX_TITLES = 5
MAX_SECTIONS = 8
MAX_HASHTAGS = 10

KEYWORDS_SCHEMA = {
    "type": "object",
    "properties": {
        "keywords": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "intent": {"type": "string", "enum": ["정보형", "비교형", "후기형", "예약형"]},
                    "reason": {"type": "string"},
                },
                "required": ["text", "intent", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["keywords"],
    "additionalProperties": False,
}

TITLES_SCHEMA = {
    "type": "object",
    "properties": {
        "titles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "hook_type": {"type": "string"},
                },
                "required": ["text", "hook_type"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["titles"],
    "additionalProperties": False,
}

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["heading", "body"],
                "additionalProperties": False,
            },
        },
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "meta_description": {"type": "string"},
    },
    "required": ["sections", "hashtags", "meta_description"],
    "additionalProperties": False,
}

SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "heading": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["heading", "body"],
    "additionalProperties": False,
}
