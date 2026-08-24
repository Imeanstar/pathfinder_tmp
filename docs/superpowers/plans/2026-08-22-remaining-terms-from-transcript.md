# 성적표 기반 남은 학기 계산 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로드맵의 "남은 학기" 목록(`remaining_terms`)이 지금은 `["2-2","3-1","3-2","4-1","4-2"]`로 하드코딩돼 있어(`app/api.py:62`, "2025학번 2학년 2학기 진입 기준" 가정) 21~26학번 확장 이후 다른 학번에겐 전부 틀린 값이다. 성적표에 실제로 찍힌 "정규학기" 개수로 `8 - n`을 계산해 남은 학기를 정확히 구한다.

**Architecture:** 학번(`admission_year`)은 이미 수강년도 최솟값으로 추론하고 있다(기존 기능, 변경 없음). 여기에 과목마다 "수강학기"(1학기/2학기/계절학기)까지 추출해서, (연도,학기) 쌍의 **개수**(계절학기 제외, 6학점 이하로 의심되는 학기는 사용자 확인 거쳐 포함 여부 결정)로 정규학기 이수 횟수 `n`을 세고, `8-n`개의 남은 학기를 자동 생성한다. 6학점 이하 학기는 "군 e-러닝처럼 정규학기가 아닌데 성적표엔 정규학기처럼 찍히는" 경우와 "그냥 그 학기에 적게 들은 정규학기"를 성적표만으로 구분할 수 없으므로, 업로드 직후 마스킹 확인 화면에서 사용자에게 직접 물어본다.

**Tech Stack:** 기존과 동일 — FastAPI + Pydantic, Gemini 성적표 구조화(`app/llm.py`), 순수 Python 계산(`app/parser.py`), 바닐라 JS(`upload.js`/`upload.html`).

## Global Constraints

- 총 학기 수는 **고정 8학기**(4년제 기준) — 과정 구분(심화/일반/복수/부전공)이나 학번과 무관하게 동일하게 적용한다(사용자 명시).
- 정규학기 판정 대상은 "1학기"/"2학기"뿐이다. "계절학기"(동계·하계)는 학점과 무관하게 **항상** 제외하고 사용자에게 묻지도 않는다(사용자 명시: "계절학기 제외").
- 6학점 이하인 정규학기(1학기/2학기)만 사용자에게 확인 질문을 띄운다. 정확한 질문 문구(사용자 명시, 그대로 사용): `"20nn년도 n학기에 이수한 학점이 너무 적어요. 정규학기가 아닌가요?"` — 드롭다운 선택지: `"정규학기입니다."` / `"정규학기가 아닙니다."`.
- 질문은 업로드 직후 마스킹 확인 화면(`upload.html`의 `#stepMasked`)에서 띄운다(사용자 명시: "성적표 분석한 바로 직후, 유저에게 컨펌 받는 창에서").
- `admission_year` 추론(연도 최솟값 기반, `app/parser.py`의 `infer_admission_year`)은 이미 구현돼 있고 이번 작업과 무관하다 — 건드리지 않는다.
- 기존 `PlanRequest.remaining_terms` 필드와 `DEFAULT_REMAINING_TERMS`는 **삭제하지 않는다** — 과목에 "semester" 정보가 하나도 없을 때(개발 모드 수동 입력 등) 쓸 폴백이다. 이 프로젝트 전체를 관통하는 "AI/추론 경로엔 항상 대체 경로가 있어야 한다" 원칙과 동일 패턴(`app/parser.py`의 `infer_admission_year` or `None` 폴백과 동일 구조).
- 확인 질문에 답하지 않으면(플레이스홀더 상태로 남아있으면) "확인했습니다 · 다음" 버튼을 막는다 — "모른다"를 추측해서 채우지 않는다는 이 프로젝트의 기존 원칙(`app/agents/session_chat.py` 등)과 동일 기조.

---

### Task 1: `app/llm.py` — 성적표 과목 추출 스키마에 "수강학기" 추가

**Files:**
- Modify: `app/llm.py` (`PROMPT_TEMPLATE`)
- Test: `tests/test_llm.py`

**Interfaces:**
- Consumes: 없음
- Produces: `PROMPT_TEMPLATE`이 요구하는 과목 JSON 스키마가 `{"name": str, "credit": number, "category": str, "year": int, "semester": str}`으로 확장됨. `semester`는 반드시 `"1학기"` / `"2학기"` / `"계절학기"` 셋 중 하나로 정규화된 문자열이어야 한다(성적표 원문이 "동계계절"/"하계계절"이어도 "계절학기"로 합쳐서 출력). Task 2가 이 필드를 읽는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_llm.py`에 추가(파일 끝, 기존 `test_prompt_template_requires_year_field_for_admission_year_inference` 함수 뒤):

```python
def test_prompt_template_requires_semester_field_normalized_to_three_values():
    # 남은 학기(8-n) 계산은 "수강학기"가 1학기/2학기/계절학기 중 뭔지 알아야 한다
    # (2026-08-22 사용자 요청 — 계절학기는 정규학기 카운트에서 항상 제외).
    assert "semester" in PROMPT_TEMPLATE
    assert "수강학기" in PROMPT_TEMPLATE
    assert "계절학기" in PROMPT_TEMPLATE
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_llm.py -k semester_field -v`
Expected: FAIL — `assert 'semester' in PROMPT_TEMPLATE`에서 AssertionError.

- [ ] **Step 3: `PROMPT_TEMPLATE` 수정**

`app/llm.py`의 `PROMPT_TEMPLATE`(현재 아래와 같이 시작함)를 통째로 다음으로 교체:

```python
PROMPT_TEMPLATE = """다음은 마스킹된 대학교 성적표 텍스트다. 이수한 과목만 골라
JSON 배열로 출력하라. 각 항목은 {{"name": 과목명, "credit": 학점(숫자),
"category": 이수구분, "year": 수강년도(4자리 정수), "semester": 수강학기}} 형태여야 한다.

아주대학교 성적표는 이수구분이 다음 약어로 찍혀 있다. 약어를 아래 풀네임으로
반드시 변환해서 "category" 값으로 써라(약어 그대로 쓰지 마라):
- "전필" -> "전공필수"
- "전선" -> "전공선택"
- "전기" -> "전공기초" (주의: "전기공학"의 "전기"가 아니다. 전공기초는 SW커리어세미나·
  확률및통계1·선형대수1처럼 전공필수/전공선택과 별도인 이수구분이다. "전공선택"으로
  잘못 바꿔 쓰지 마라.)
- "교필" -> "교양필수"
- "교선" -> "교양선택"
- "일선" -> "일반선택"
위 6개 약어 외의 표기(전공필수/전공선택 등 이미 풀네임인 경우)는 그대로 쓰면 된다.

"year"는 그 과목 행의 "수강년도" 컬럼 값을 그대로 숫자로 옮겨 적어라(예: "2021 1학기"면
year는 2021).

"semester"는 같은 행의 "수강학기" 컬럼을 아래 세 값 중 정확히 하나로 정규화해서 써라:
- "1학기"
- "2학기"
- "계절학기" (원문이 "동계계절", "하계계절", "여름계절학기" 등 계절학기 표기이면 전부
  이 값 하나로 합쳐라 — 동계/하계를 구분하지 마라)

year 또는 semester를 알 수 없는 행은 통째로 건너뛰어라.

설명이나 다른 텍스트 없이 JSON 배열만 출력하라.

--- 성적표 텍스트 ---
{masked_text}
"""
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_llm.py -v`
Expected: 전부 PASS(기존 `test_call_gemini_parses_json_array_wrapped_in_code_fence`는 `PROMPT_TEMPLATE` 내용이 아니라 `_call_gemini`의 파싱 동작만 검증하므로 영향 없음).

- [ ] **Step 5: 커밋**

```bash
git add app/llm.py tests/test_llm.py
git commit -m "feat: 성적표 과목 추출에 수강학기(1/2학기/계절학기) 필드 추가"
```

---

### Task 2: `app/parser.py` — 저학점 의심 학기 탐지 + 남은 학기 계산

**Files:**
- Modify: `app/parser.py`
- Test: `tests/test_parser.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `find_low_credit_semesters(courses: list[dict], threshold: int = 6) -> list[dict]` — 반환 항목은 `{"year": int, "semester": str, "credit_sum": int}`(연도·학기 오름차순 정렬). "semester"가 "1학기"/"2학기"인 행만 대상이고(계절학기는 애초에 제외), 같은 (year, semester)의 credit 합이 `threshold` 이하인 것만 담는다. Task 4가 이 목록으로 화면1 확인 질문을 만든다.
  - `compute_remaining_terms(courses: list[dict], semester_overrides: dict[str, bool] | None = None) -> list[str] | None` — 과목 중 하나라도 `"semester"` 키가 없으면(개발 모드 수동 입력 등, 계산 불가) `None`을 돌려준다(추측하지 않는다). 계산 가능하면: (year, semester)가 "1학기"/"2학기"인 것만 모아 credit 합을 구하고, `find_low_credit_semesters`와 같은 기준(6학점 이하)으로 걸리는 학기는 `semester_overrides`(키는 `f"{year}-{semester}"`, 예: `"2024-1학기"`)에서 `False`로 명시된 것만 정규학기 카운트에서 제외한다(명시 안 돼 있으면 정규학기로 간주 — 화면이 응답을 안 보내는 경우는 없지만, 서버 단독 호출 시 안전한 기본값). `n` = 남은(제외 안 된) 고유 (year,semester) 개수. `remaining = max(0, 8 - n)`이고, `admission_year`(= `infer_admission_year(courses)`, 이미 구현됨)를 기준으로 인덱스 `n`부터 7까지 `f"{grade}-{sem}"` 형태로 8학기 중 남은 것만 리스트로 돌려준다(`grade = i//2+1`, `sem = i%2+1`). Task 3이 이 함수를 가져다 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_parser.py` 맨 끝에 추가:

```python
from app.parser import compute_remaining_terms, find_low_credit_semesters


def test_find_low_credit_semesters_flags_regular_semester_at_or_below_threshold():
    courses = [
        {"name": "A", "credit": 3, "category": "전공필수", "year": 2024, "semester": "1학기"},
        {"name": "B", "credit": 3, "category": "전공선택", "year": 2024, "semester": "1학기"},
        {"name": "C", "credit": 3, "category": "전공선택", "year": 2021, "semester": "1학기"},
        {"name": "D", "credit": 15, "category": "전공선택", "year": 2021, "semester": "1학기"},
    ]
    flagged = find_low_credit_semesters(courses)
    assert flagged == [{"year": 2024, "semester": "1학기", "credit_sum": 6}]


def test_find_low_credit_semesters_ignores_season_sessions_regardless_of_credit():
    # 계절학기는 학점이 낮아도(원래 그런 것이므로) 절대 질의 대상이 아니다.
    courses = [
        {"name": "겨울특강", "credit": 3, "category": "전공선택", "year": 2024, "semester": "계절학기"},
    ]
    assert find_low_credit_semesters(courses) == []


def test_find_low_credit_semesters_empty_when_all_semesters_above_threshold():
    courses = [
        {"name": "A", "credit": 15, "category": "전공필수", "year": 2021, "semester": "1학기"},
    ]
    assert find_low_credit_semesters(courses) == []


def test_compute_remaining_terms_counts_regular_semesters_and_returns_eight_minus_n():
    # 사용자 예시: 25학번이 2025-1, 2025-2만 이수(정규학기 2개) -> 8-2=6학기 남음,
    # 3학년 1학기(인덱스 2)부터 시작해야 한다.
    courses = [
        {"name": "A", "credit": 18, "category": "전공필수", "year": 2025, "semester": "1학기"},
        {"name": "B", "credit": 18, "category": "전공필수", "year": 2025, "semester": "2학기"},
    ]
    assert compute_remaining_terms(courses) == ["2-1", "2-2", "3-1", "3-2", "4-1", "4-2"]


def test_compute_remaining_terms_excludes_season_sessions_from_count():
    courses = [
        {"name": "A", "credit": 18, "category": "전공필수", "year": 2025, "semester": "1학기"},
        {"name": "B", "credit": 3, "category": "전공선택", "year": 2025, "semester": "계절학기"},
    ]
    # 계절학기는 세지 않으므로 정규학기 1개 -> 8-1=7학기, 1학년 2학기(인덱스 1)부터.
    assert compute_remaining_terms(courses) == ["1-2", "2-1", "2-2", "3-1", "3-2", "4-1", "4-2"]


def test_compute_remaining_terms_excludes_semester_confirmed_as_not_regular():
    # 사용자 본인 사례: 2021-1~2022-2(4개 정규학기) 이수 후 휴학 중 군e-러닝으로
    # 2024-1·2024-2가 성적표에 찍혔지만 정규학기가 아니라고 확인한 경우.
    courses = [
        {"name": "A", "credit": 18, "category": "전공필수", "year": 2021, "semester": "1학기"},
        {"name": "B", "credit": 18, "category": "전공필수", "year": 2021, "semester": "2학기"},
        {"name": "C", "credit": 18, "category": "전공필수", "year": 2022, "semester": "1학기"},
        {"name": "D", "credit": 18, "category": "전공필수", "year": 2022, "semester": "2학기"},
        {"name": "E", "credit": 3, "category": "전공선택", "year": 2024, "semester": "1학기"},
        {"name": "F", "credit": 3, "category": "전공선택", "year": 2024, "semester": "2학기"},
    ]
    overrides = {"2024-1학기": False, "2024-2학기": False}
    # 정규학기 4개만 인정 -> 8-4=4학기 남음, 3학년 1학기(인덱스 4)부터.
    assert compute_remaining_terms(courses, overrides) == ["3-1", "3-2", "4-1", "4-2"]


def test_compute_remaining_terms_counts_unanswered_low_credit_semester_as_regular_by_default():
    # semester_overrides에 명시 안 된 저학점 학기는(화면 흐름상 항상 답하게 막지만, 이
    # 함수 자체는 서버 단독 호출도 안전해야 하므로) 정규학기로 간주한다 — 8-2=6학기.
    courses = [
        {"name": "A", "credit": 18, "category": "전공필수", "year": 2025, "semester": "1학기"},
        {"name": "B", "credit": 3, "category": "전공선택", "year": 2025, "semester": "2학기"},
    ]
    assert compute_remaining_terms(courses) == ["2-1", "2-2", "3-1", "3-2", "4-1", "4-2"]


def test_compute_remaining_terms_returns_none_when_semester_field_missing():
    # 개발 모드 수동 입력 등 semester 정보가 아예 없으면 추측하지 않고 None(폴백 유도).
    courses = [{"name": "A", "credit": 3, "category": "전공필수", "year": 2025}]
    assert compute_remaining_terms(courses) is None


def test_compute_remaining_terms_clamps_to_empty_when_eight_or_more_regular_semesters():
    courses = [
        {"name": f"C{i}", "credit": 18, "category": "전공필수", "year": 2021 + i // 2, "semester": "1학기" if i % 2 == 0 else "2학기"}
        for i in range(9)
    ]
    assert compute_remaining_terms(courses) == []
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_parser.py -k "low_credit_semesters or compute_remaining_terms" -v`
Expected: 전부 FAIL — `ImportError: cannot import name 'compute_remaining_terms' from 'app.parser'`.

- [ ] **Step 3: 함수 구현**

`app/parser.py`의 `infer_admission_year` 함수(Task 4, 이전 계획에서 이미 구현됨) 바로 뒤에 추가:

```python
_REGULAR_SEMESTERS = ("1학기", "2학기")


def _semester_key(year: int, semester: str) -> str:
    return f"{year}-{semester}"


def _regular_semester_credit_sums(courses: list[dict]) -> dict[tuple[int, str], int]:
    sums: dict[tuple[int, str], int] = {}
    for c in courses:
        semester = c.get("semester")
        if semester not in _REGULAR_SEMESTERS:
            continue  # 계절학기 또는 정보 없음 — 정규학기 후보가 아니다
        key = (c["year"], semester)
        sums[key] = sums.get(key, 0) + c["credit"]
    return sums


def find_low_credit_semesters(courses: list[dict], threshold: int = 6) -> list[dict]:
    """1학기/2학기인데 학점 합이 threshold 이하인 학기를 찾는다. 우리 학교엔 최소수강학점
    제도가 없어 "진짜 적게 들은 정규학기"와 "군 e-러닝처럼 성적표엔 정규학기로 찍히지만
    실제로는 정규학기가 아닌 경우"를 성적표만으로 구분할 수 없다 — 그래서 사용자에게
    직접 물어본다(2026-08-22 사용자 지시). 계절학기는 학점과 무관하게 애초에 후보에서
    빠진다(_regular_semester_credit_sums가 이미 걸러냄)."""
    sums = _regular_semester_credit_sums(courses)
    flagged = [
        {"year": year, "semester": semester, "credit_sum": total}
        for (year, semester), total in sums.items()
        if total <= threshold
    ]
    flagged.sort(key=lambda f: (f["year"], f["semester"]))
    return flagged


def compute_remaining_terms(
    courses: list[dict], semester_overrides: dict[str, bool] | None = None
) -> list[str] | None:
    """입학년도로부터 "정규학기를 몇 번 이수했는가"(n)를 세어 8-n개의 남은 학기를
    돌려준다(2026-08-22 사용자 지시) — 달력상 몇 년이 지났는지가 아니라 실제로 이수한
    정규학기 수만 본다(휴학 기간은 성적표에 아예 안 남으므로 자동으로 제외된다).

    semester_overrides: find_low_credit_semesters()가 찾아낸 저학점 학기 중 사용자가
    "정규학기가 아닙니다"라고 답한 것만 f"{year}-{semester}" 키로 False를 넣어 넘긴다.
    답하지 않은 저학점 학기는 정규학기로 간주한다(화면 흐름상 항상 답하게 막지만, 이
    함수 자체가 서버 단독 호출에도 안전해야 하므로 — 모른다고 0으로 깎지 않는다).

    과목에 "semester" 정보가 하나도 없으면(개발 모드 수동 입력 등) 계산할 수 없으므로
    추측하지 않고 None을 돌려준다 — 호출자가 기존 기본값으로 폴백해야 한다."""
    if not any("semester" in c for c in courses):
        return None

    overrides = semester_overrides or {}
    sums = _regular_semester_credit_sums(courses)
    regular_count = sum(
        1 for (year, semester) in sums if overrides.get(_semester_key(year, semester), True)
    )

    start_index = min(regular_count, 8)  # 8개 이상 이수했으면 남은 학기 없음(range가 비어 [])
    return [f"{i // 2 + 1}-{i % 2 + 1}" for i in range(start_index, 8)]


def extract_words_from_pdf(pdf_bytes: bytes) -> list[dict]:
```

(`infer_admission_year`가 이미 같은 파일에 정의돼 있으므로 새 import는 필요 없다. `extract_words_from_pdf`의 기존 정의 줄 바로 앞에 위 함수들을 끼워 넣고, 원래 있던 `def extract_words_from_pdf(pdf_bytes: bytes) -> list[dict]:` 줄은 그대로 이어진다 — 실수로 중복 작성하지 않도록 주의.)

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_parser.py -v`
Expected: 전부 PASS.

- [ ] **Step 5: 커밋**

```bash
git add app/parser.py tests/test_parser.py
git commit -m "feat: 성적표 정규학기 수로 남은 학기(8-n) 계산 + 저학점 학기 탐지"
```

---

### Task 3: `app/api.py` — 저학점 학기 확인 질문 + 남은 학기 자동 계산 연결

**Files:**
- Modify: `app/api.py` (`/api/upload` 응답, `PlanRequest`, `/api/plan` 핸들러)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `find_low_credit_semesters`, `compute_remaining_terms` (Task 2, `app/parser.py`)
- Produces: `/api/upload` 응답에 `"low_credit_semesters": list[dict]` 추가(항상 포함, 비어있을 수 있음). `PlanRequest`에 `irregular_semester_answers: dict[str, bool] = {}` 필드 추가(키 `f"{year}-{semester}"`, 값 `True`="정규학기입니다"/`False`="정규학기가 아닙니다"). `/api/plan`이 `req.remaining_terms`(기존 기본값 폴백) 대신 `compute_remaining_terms(req.courses, req.irregular_semester_answers) or req.remaining_terms`로 실제 배치에 쓸 학기를 정한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_api.py`에서 `def test_upload_includes_inferred_admission_year_in_response(monkeypatch):` 함수 뒤에 추가:

```python
def test_upload_includes_low_credit_semesters_in_response(monkeypatch):
    monkeypatch.setattr(
        "app.api.parse_transcript",
        lambda pdf_bytes, structure_fn: TranscriptData(
            courses=[
                {"name": "이산수학", "credit": 3, "category": "전공필수", "year": 2024, "semester": "1학기"},
                {"name": "자료구조", "credit": 3, "category": "전공필수", "year": 2024, "semester": "1학기"},
                {"name": "알고리즘", "credit": 18, "category": "전공필수", "year": 2021, "semester": "1학기"},
            ],
            masked_text="dummy",
        ),
    )
    res = client.post("/api/upload", files={"file": ("t.pdf", b"%PDF-1.4", "application/pdf")})
    assert res.status_code == 200
    assert res.json()["low_credit_semesters"] == [
        {"year": 2024, "semester": "1학기", "credit_sum": 6}
    ]


def test_plan_computes_remaining_terms_from_transcript_regular_semester_count():
    # 2025-1, 2025-2만 이수(정규학기 2개) -> 8-2=6학기, 2학년 1학기부터 시작해야 한다.
    payload = {
        "courses": [
            {"name": "이산수학", "credit": 18, "category": "전공필수", "year": 2025, "semester": "1학기"},
            {"name": "자료구조", "credit": 18, "category": "전공필수", "year": 2025, "semester": "2학기"},
        ],
        "admission_year": 2025,
        "track_type": "심화과정",
        "track": "백엔드",
    }
    res = client.post("/api/plan", json=payload)
    assert res.status_code == 200
    assert set(res.json()["roadmap"]["schedule"].keys()) == {"2-1", "2-2", "3-1", "3-2", "4-1", "4-2"}


def test_plan_excludes_semester_answered_as_not_regular():
    payload = {
        "courses": [
            {"name": "이산수학", "credit": 18, "category": "전공필수", "year": 2021, "semester": "1학기"},
            {"name": "자료구조", "credit": 18, "category": "전공필수", "year": 2021, "semester": "2학기"},
            {"name": "군이러닝1", "credit": 3, "category": "전공선택", "year": 2024, "semester": "1학기"},
        ],
        "admission_year": 2021,
        "track_type": "심화과정",
        "track": "백엔드",
        "irregular_semester_answers": {"2024-1학기": False},
    }
    res = client.post("/api/plan", json=payload)
    # 정규학기 2개만 인정 -> 8-2=6학기, 2학년 1학기부터.
    assert set(res.json()["roadmap"]["schedule"].keys()) == {"2-1", "2-2", "3-1", "3-2", "4-1", "4-2"}


def test_plan_falls_back_to_request_remaining_terms_when_semester_data_missing():
    # 기존 동작 100% 호환 — courses에 semester가 하나도 없으면(개발 모드 등)
    # req.remaining_terms(기본값)를 그대로 쓴다.
    payload = {
        "courses": [], "admission_year": 2025, "track_type": "심화과정", "track": "백엔드",
    }
    res = client.post("/api/plan", json=payload)
    assert set(res.json()["roadmap"]["schedule"].keys()) == {"2-2", "3-1", "3-2", "4-1", "4-2"}
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_api.py -k "low_credit_semesters or remaining_terms_from_transcript or answered_as_not_regular" -v`
Expected: `low_credit_semesters` 테스트는 `KeyError`로 FAIL. 나머지 두 개는 원래 하드코딩된 `DEFAULT_REMAINING_TERMS`를 그대로 쓰므로, 기대한 학기 집합과 달라 FAIL(예: `2-1`이 없고 `2-2`가 있는 식). `falls_back` 테스트는 지금도 이미 그 값이라 PASS일 수 있다 — 그래도 같이 실행해 회귀를 확인한다.

- [ ] **Step 3: `/api/upload` 핸들러 수정**

`app/api.py` 상단 import에서 `from app.parser import InjectionDetected, TranscriptData, infer_admission_year, parse_transcript`를 다음으로 교체:

```python
from app.parser import (
    InjectionDetected,
    TranscriptData,
    compute_remaining_terms,
    find_low_credit_semesters,
    infer_admission_year,
    parse_transcript,
)
```

`/api/upload`의 `response = {...}` 블록(`"admission_year": infer_admission_year(transcript.courses),` 바로 뒤)에 추가:

```python
        "low_credit_semesters": find_low_credit_semesters(transcript.courses),
```

- [ ] **Step 4: `PlanRequest`에 필드 추가**

`PlanRequest`의 `remaining_terms: list[str] = DEFAULT_REMAINING_TERMS` 줄 바로 뒤에 추가:

```python
    # 화면1 마스킹 확인 단계에서 사용자가 "정규학기가 아닙니다"라고 답한 저학점
    # 학기만 담긴다(키: f"{year}-{semester}", 값 False). 나머지는 그대로 정규학기로
    # 간주한다(2026-08-22).
    irregular_semester_answers: dict[str, bool] = {}
```

- [ ] **Step 5: `/api/plan` 핸들러 수정**

`resolved_admission_year = infer_admission_year(req.courses) or req.admission_year` 줄 바로 뒤에 추가:

```python
    resolved_remaining_terms = (
        compute_remaining_terms(req.courses, req.irregular_semester_answers) or req.remaining_terms
    )
```

`run_full_plan(...)` 호출부의 `remaining_terms=req.remaining_terms,`를 다음으로 교체:

```python
        remaining_terms=resolved_remaining_terms,
```

- [ ] **Step 6: 테스트 실행해서 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_api.py -v`
Expected: 전부 PASS.

Run: `.venv/bin/python -m pytest -q`
Expected: 전체 스위트 PASS.

- [ ] **Step 7: 커밋**

```bash
git add app/api.py tests/test_api.py
git commit -m "feat: /api/upload·/api/plan이 성적표 정규학기 수로 남은 학기를 계산"
```

---

### Task 4: 화면1 — 저학점 학기 확인 질문 UI

**Files:**
- Modify: `app/static/upload.html` (`#stepMasked` 섹션)
- Modify: `app/static/js/upload.js` (`renderMaskResult`, `confirmMaskBtn` 리스너, `handleSubmit`의 payload)

**Interfaces:**
- Consumes: Task 3의 `/api/upload` 응답 `body.low_credit_semesters`
- Produces: `/api/plan` 페이로드에 `irregular_semester_answers`(Task 3의 `PlanRequest` 필드와 정확히 같은 형태: `{"2024-1학기": false}`)를 포함시켜 보낸다. 답 안 한 저학점 학기가 있으면 "확인했습니다 · 다음" 버튼을 막는다.

- [ ] **Step 1: `upload.html`에 질문 섹션 마크업 추가**

`app/static/upload.html`의 `#courseSection` 블록(`</div>` 닫는 줄, `<div class="wizard-actions">` 바로 앞) 뒤에 추가:

```html
        <div id="irregularSemesterSection" hidden>
          <div class="mask-section-label">확인이 필요합니다</div>
          <div id="irregularSemesterRows"></div>
        </div>

        <div class="wizard-actions">
```

(기존 `<div class="wizard-actions">` 줄은 그대로 두고 그 바로 앞에 새 섹션만 끼워 넣는다 — 중복 작성 주의.)

`app/static/css/style.css`에 새 클래스 추가(파일 끝에 추가):

```css
.irregular-semester-row {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 12px 14px; margin-bottom: 8px;
  background: var(--blue-50, #eef4ff); border-radius: 10px;
}
.irregular-semester-row p { margin: 0; flex: 1 1 260px; font-size: 14px; color: var(--navy-900, #14213c); }
.irregular-semester-row select { flex: 0 0 auto; }
```

- [ ] **Step 2: `upload.js`에 렌더링·검증 로직 추가**

`app/static/js/upload.js`의 `let uploadedCourses = [];` 바로 뒤(`let detectedAdmissionYear = null;` 다음)에 변수 추가:

```javascript
let lowCreditSemesters = [];
```

`renderMaskResult` 함수(현재 `document.getElementById("courseTableBody").innerHTML = ...` 블록으로 끝남) 끝에 다음 함수를 추가:

```javascript
function renderIrregularSemesterQuestions(lowCredit) {
  lowCreditSemesters = lowCredit || [];
  const section = document.getElementById("irregularSemesterSection");
  const rows = document.getElementById("irregularSemesterRows");

  if (lowCreditSemesters.length === 0) {
    section.hidden = true;
    rows.innerHTML = "";
    return;
  }

  section.hidden = false;
  rows.innerHTML = lowCreditSemesters
    .map(
      (s, i) => `
      <div class="irregular-semester-row">
        <p>${s.year}년도 ${s.semester}에 이수한 학점(${s.credit_sum}학점)이 너무 적어요. 정규학기가 아닌가요?</p>
        <select data-irregular-idx="${i}" data-year="${s.year}" data-semester="${s.semester}">
          <option value="">선택해주세요</option>
          <option value="regular">정규학기입니다.</option>
          <option value="not_regular">정규학기가 아닙니다.</option>
        </select>
      </div>`
    )
    .join("");
}

function collectIrregularSemesterAnswers() {
  const answers = {};
  document.querySelectorAll("#irregularSemesterRows select").forEach((sel) => {
    if (!sel.value) return;
    answers[`${sel.dataset.year}-${sel.dataset.semester}`] = sel.value === "regular";
  });
  return answers;
}

function allIrregularSemestersAnswered() {
  if (lowCreditSemesters.length === 0) return true;
  const selects = document.querySelectorAll("#irregularSemesterRows select");
  return Array.from(selects).every((sel) => sel.value !== "");
}
```

`renderMaskResult` 함수 안, `if (body.warning) { ... return; }` 블록 바로 뒤(`courseSection.hidden = false;` 앞)에 호출 추가:

```javascript
  renderIrregularSemesterQuestions(body.low_credit_semesters);
```

- [ ] **Step 3: "확인했습니다 · 다음" 클릭 시 검증 + `handleSubmit` payload에 답변 포함**

`app/static/js/upload.js`의 `document.getElementById("confirmMaskBtn").addEventListener("click", () => { goToStep("stepMasked", "stepSettings"); });`를 다음으로 교체:

```javascript
  document.getElementById("confirmMaskBtn").addEventListener("click", () => {
    if (!allIrregularSemestersAnswered()) {
      alert("아직 답하지 않은 학기가 있습니다. 전부 답해주세요.");
      return;
    }
    goToStep("stepMasked", "stepSettings");
  });
```

`handleSubmit`의 `const payload = { ... };` 블록에서 `email_hash: emailHash,` 바로 뒤에 추가:

```javascript
    irregular_semester_answers: collectIrregularSemesterAnswers(),
```

- [ ] **Step 4: 헤드리스 브라우저로 검증**

```bash
SCRATCH="/private/tmp/claude-501/-Users-minwoo-Documents-Study-AI------2------/600265f2-a15e-4a4d-bfbc-4fd9b26db127/scratchpad"
curl -s http://127.0.0.1:9333/json/version >/dev/null || \
  ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    --headless=new --remote-debugging-port=9333 --no-first-run --no-default-browser-check \
    --disable-gpu --user-data-dir="$SCRATCH/chrome-profile-verify8" \
    > "$SCRATCH/chrome_verify8.log" 2>&1 & disown)
sleep 2
```

uvicorn을 재시작해 최신 코드를 반영한 뒤(`pkill -f "uvicorn app.api:app"` → 재실행), 기존 `cdp_task6.js` 패턴을 참고해:
1. `upload.html`을 로드하고 `renderMaskResult({ courses: [...], low_credit_semesters: [{year:2024, semester:"1학기", credit_sum:6}] })`를 직접 호출(또는 `body`를 흉내내 동일 로직 재현)해 `#irregularSemesterSection`이 보이고 질문 문구·드롭다운이 정확히 뜨는지 확인.
2. 드롭다운을 답하지 않은 채 `#confirmMaskBtn`을 클릭해도 `stepSettings`로 안 넘어가는지(`alert` 스텁 필요 — `window.alert = () => {}`로 오버라이드 후 `stepMasked`가 여전히 보이는지로 판단) 확인.
3. 드롭다운에 "정규학기가 아닙니다"를 선택한 뒤 클릭하면 `stepSettings`로 넘어가는지, `collectIrregularSemesterAnswers()`가 `{"2024-1학기": false}`를 돌려주는지 확인.

Expected: 세 가지 모두 기대한 대로 동작.

- [ ] **Step 5: 커밋**

```bash
git add app/static/upload.html app/static/js/upload.js app/static/css/style.css
git commit -m "feat: 저학점 학기 확인 질문 UI(화면1 마스킹 확인 단계)"
```

---

## Self-Review 메모

- **스펙 커버리지**: "8-n" 공식 → Task 2 `compute_remaining_terms`. 계절학기 항상 제외 → Task 2 `_regular_semester_credit_sums`. 6학점 이하만 질의 → Task 2 `find_low_credit_semesters` + Task 4 UI. 질문 문구·드롭다운 문구(사용자 명시 그대로) → Task 4 Step 2. 질문 위치(업로드 직후 마스킹 확인 화면) → Task 4 Step 1(`#stepMasked`). 답 안 하면 진행 불가 → Task 4 Step 3 `allIrregularSemestersAnswered`. 성적표 없는 정보(휴학 기간)로 추측하지 않음 → 휴학 학기는 애초에 성적표에 안 남아 자동으로 카운트에서 빠짐(추가 코드 불필요, 자연히 성립).
- **플레이스홀더 스캔**: 없음 — 전 Task 코드·테스트 완전한 값으로 채움.
- **타입 일관성**: `find_low_credit_semesters(courses, threshold=6) -> list[dict]`가 Task 2에서 정의되고 Task 3의 `app/api.py`에서 동일 시그니처로 호출됨. `compute_remaining_terms(courses, semester_overrides=None) -> list[str] | None`이 Task 2에서 정의되고 Task 3에서 `req.irregular_semester_answers`(dict[str,bool])를 그대로 `semester_overrides` 인자로 전달 — 키 형식(`f"{year}-{semester}"`)이 Task 2의 `_semester_key`와 Task 3의 `PlanRequest.irregular_semester_answers` 주석, Task 4의 `collectIrregularSemesterAnswers()`(`` `${sel.dataset.year}-${sel.dataset.semester}` ``) 세 곳 모두 동일하게 일치.
