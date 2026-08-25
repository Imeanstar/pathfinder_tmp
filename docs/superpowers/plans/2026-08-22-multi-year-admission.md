# 21~26학번 다년도 졸업요건 확장 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 지금 2025학번으로 고정된 졸업요건 판정을 21~26학번 전체로 확장한다. 학번마다 총 졸업학점·전공필수 과목 리스트·전공선택/전공기초 학점 기준·산학프로젝트 인증 규칙·현장실습 학점 상한·어학 기준이 다르며, 새로 "전공기초"(25학번부터 신설, 7학점) 요건도 별도로 추적한다.

**Architecture:** `data/graduation_requirements.json`이 학번(문자열 키)별 요건을 담고, `app/audit.py`가 성적표에서 파싱된 과목의 `category`(전공필수/전공선택/전공기초/교양필수/교양선택/일반선택)로 각 풀의 학점을 합산해 그 학번 요건과 비교한다. 학번(`admission_year`)은 사용자가 화면에서 입력하지 않고, 성적표의 각 과목 행에 찍힌 "수강년도"(신입생은 1학년 1학기 휴학이 교칙상 불가하므로 최솟값이 곧 입학년도) 중 최솟값으로 서버가 자동으로 추론한다.

**Tech Stack:** FastAPI + Python(dataclass 기반 도메인 모델), Gemini(`google-genai`)로 마스킹된 성적표 텍스트→과목 리스트 구조화, 순수 Python 판정 로직(LLM 미사용), 바닐라 JS 프론트엔드.

## Global Constraints

- TDD 필수 — 모든 프로덕션 코드 변경 전 실패하는 테스트를 먼저 작성하고 실패를 확인한 뒤 구현한다(RED→GREEN).
- 실제 성적표(`성적표.pdf`)의 이수구분은 이미 "전필/전선/전기/교필/교선/일선" 약어로 찍혀 있고, 이 약어는 **응시 학기 시점** 기준이지 학생의 입학년도 기준이 아니다 — 즉 과목별 `category`는 성적표 원문을 그대로 신뢰하면 되고, `admission_year`는 오직 졸업요건 기준표(총학점/필수 리스트/문턱값/인증 규칙) 조회에만 쓰인다.
- 요람 원문 근거는 `요럄/2021 요람.pdf` ~ `요럄/2026 요람.pdf`(모두 "소프트웨어및컴퓨터공학전공" 챕터 발췌본, pdfplumber로 원문 대조 완료). 아래 각 학번 데이터는 전부 원문 텍스트로 재확인한 값이다 — 추측치 없음.
- "전기" 약어는 "전공기초"를 뜻한다 — "전기공학"과 혼동하지 않도록 프롬프트에 명시한다(Task 3).
- `data/courses.json`(과목 카탈로그, 로드맵 추천용)은 이번 작업에서 건드리지 않는다 — 카탈로그의 `category`는 로드맵 추천 풀(전공선택 후보) 필터링에만 쓰이고 졸업 판정에는 전혀 쓰이지 않는다(`app/audit.py`는 항상 학생의 파싱된 성적표 과목 `category`만 본다). 확률및통계1·선형대수1·SW커리어세미나는 카탈로그에 아예 없는데, 이는 어느 학번에서도 이 과목들이 "선택 가능한 전공선택 풀"의 일부가 아니므로(21~24는 전공학점 미인정, 25+는 고정된 전공기초 3과목) 이미 올바른 상태다.
- 로드맵 스케줄링(`app/agents/roadmap.py`)에 전공기초 3과목을 학기별로 자동 배치하는 기능은 이번 범위 밖이다 — 이번 작업은 감사(audit) 판정과 졸업 현황 카드 표시까지만 다룬다. (전공선택도 개별 과목 단위로 스케줄링되지 않고 `course_reco.py`의 추천 풀로만 다뤄지는 기존 패턴과 동일한 수준으로 맞춘 것.)

---

## 확정된 학번별 데이터 (원문 재확인 완료)

### 그룹 A — 2021, 2022학번 (완전히 동일)
- `total_credit`: 140
- `required_major_courses`(11개, 36학점): 컴퓨터프로그래밍및실습(4), 이산수학(3), 창의소프트웨어입문(3), 디지털회로(3), 객체지향프로그래밍및실습(4), 자료구조(3), 컴퓨터구조(3), 알고리즘(3), 시스템프로그래밍및실습(4), 컴퓨터네트워크(3), 운영체제(3)
- `elective_major_credit`: 심화과정 37, 일반과정 10, 복수과정 10
- `major_foundation_credit`: 없음(이 학번엔 "전공기초"라는 요건 자체가 없다 — 확률및통계1/선형대수1/SW커리어세미나/수학1·2/기초과학은 전부 "교필"로 찍혀 전공 학점으로 전혀 인정 안 됨)
- `industry_project_certification`: 심화과정만 `min_courses: 2`. **일반과정·복수과정은 완전 면제**(원문의 "기타 졸업요건" 전체가 "(심화과정 이수 시 필수)"로 통째로 게이트돼 있어 일반과정엔 이 요건 자체가 없다) → `min_courses: 0`으로 표현(0과목이면 항상 충족 판정되므로 "면제"와 동치).
- `elective_credit_cap_groups`: 없음(현장실습 학점 상한 자체가 없던 시절 — 무제한 인정)
- `language_requirement`: 아래 "모든 학번 공통" 참고(학번별 차이 없음)

### 그룹 B — 2023, 2024학번 (완전히 동일)
- `total_credit`: 140
- `required_major_courses`(11개, 36학점): 컴퓨터프로그래밍및실습(4), 이산수학(3), **인공지능입문(3)**(창의소프트웨어입문 대체), 디지털회로(3), 객체지향프로그래밍및실습(4), 자료구조(3), 컴퓨터구조(3), 알고리즘(3), 시스템프로그래밍및실습(4), 컴퓨터네트워크(3), 운영체제(3)
- `elective_major_credit`: 심화과정 37, 일반과정 10, 복수과정 10
- `major_foundation_credit`: 없음(그룹 A와 동일한 이유)
- `industry_project_certification`: 심화과정 `min_courses: 2`, 일반과정 `min_courses: 1`, 복수과정 `min_courses: 1`(2023학번부터 일반과정도 의무 생김)
- `elective_credit_cap_groups`: 현장실습군(SW현장실습1~6, 창업실습1·2, 창업현장실습1·2) 최대 **12학점**까지만 전공선택 인정
- `language_requirement`: 아래 "모든 학번 공통" 참고(학번별 차이 없음)

### 2025학번 (기존 데이터 — Task 1에서 `major_foundation_credit` 키만 추가)
- 이미 `data/graduation_requirements.json`에 정확히 들어있음(원문 대조로 재확인 완료: `total_credit` 128, `required_major_courses` 10개 32학점, `elective_major_credit` 심화32/일반10/복수10, `industry_project_certification` 심화2/일반1/복수1, `elective_credit_cap_groups` 현장실습군 최대 6학점, `language_requirement` TOEIC_Speaking "IM1").
- 유일하게 빠진 것: `major_foundation_credit`(전공기초 = SW커리어세미나(1)+확률및통계1(3)+선형대수1(3) = 7학점) — 심화과정 7, 일반과정 7, 복수과정 6, 부전공 6.

### 2026학번 (신규 — 2025와 다른 점 주의)
- `total_credit`: 128
- `required_major_courses`(**9개, 29학점** — 2025와 다름! **인공지능입문이 빠짐**): 컴퓨터프로그래밍및실습(4), 이산수학(3), 객체지향프로그래밍및실습(4), 자료구조(3), 컴퓨터구조(3), 알고리즘(3), 컴퓨터네트워크(3), 시스템프로그래밍(3), 운영체제(3)
- `elective_major_credit`: 심화과정 32, 일반과정 10, 복수과정 10 (2025와 동일)
- `major_foundation_credit`: 심화 7, 일반 7, 복수 6, 부전공 6 (2025와 동일 — SW커리어세미나(1)+확률및통계1(3)+선형대수1(3), 단 26학번부턴 확률및통계1·선형대수1 둘 다 필수, "택1" 아님)
- `industry_project_certification`: 심화 2, 일반 1, 복수 1 (2025와 동일)
- `elective_credit_cap_groups`: 현장실습군 최대 6학점 (2025와 동일)
- `language_requirement`: 아래 "모든 학번 공통" 참고(학번별 차이 없음)

### 어학 기준 — 학번이 아니라 "졸업요건이 바뀐 게 아니라, 외부 공인시험 자체가 신구 버전으로 개편되면서 둘 다 인정"

처음엔 26학번 요람의 TEPS 329·TOEIC Speaking IM1 값을 "학번별 어학 기준 차이"로 오인했으나, 사용자가 학교 공식 어학 기준표 이미지를 제공해 정정함(2026-08-22). **졸업 사정의 어학 기준 자체는 21~26학번 전부 동일**하고, TEPS와 TOEIC Speaking만 신·구 시험 버전을 **둘 다 인정**한다 — 학생이 어느 쪽을 응시했든 그 버전 기준만 넘기면 된다. IELTS도 원래부터 인정 시험이었는데(별도 요람 발췌본엔 안 나와 있었음) 이번에 처음 반영한다.

모든 학번에 아래 **하나의** `language_requirement`를 그대로 쓴다(연도별 분기 없음):

```json
"language_requirement": {
  "TOEIC": 730,
  "TEPS": 605,
  "TEPS_NEW": 329,
  "TOEFL_PBT": 534,
  "TOEFL_CBT": 200,
  "TOEFL_iBT": 72,
  "GTELP_Lv2": 67,
  "GTELP_Lv3": 89,
  "TOEIC_Speaking_OLD": 5,
  "TOEIC_Speaking": "IM1",
  "OPIc": "IL",
  "IELTS": 5.5
}
```

- `TEPS`(구 텝스, 605점)와 `TEPS_NEW`(뉴텝스, 329점) — 둘 중 하나만 넘으면 충족.
- `TOEIC_Speaking_OLD`(구 토익스피킹, 숫자 등급 Level 1~8, 5 이상)와 `TOEIC_Speaking`(신 토익스피킹, IM1/IM2/IM3처럼 문자+숫자 등급, IM1 이상) — 둘 중 하나만 넘으면 충족. `TOEIC_Speaking_OLD`를 숫자(문자열 아님)로 저장한 이유는 `app/agents/session_chat.py`의 `evaluate_language_score`가 **문자열 threshold만 등급 서열 비교를 타고, 숫자 threshold는 그냥 `float(score) >= float(threshold)`로 비교**하기 때문(`app/agents/session_chat.py:71-89`) — `5`를 숫자로 넣으면 기존 비교 코드를 한 줄도 안 고치고 바로 동작한다.
- `IELTS`도 숫자(5.5)라 같은 이유로 기존 코드 그대로 동작한다.

### 모든 학번 공통
- `min_gpa`: 2.0
- `requires_double_major_or_minor`: ["일반과정", "복수과정"] (기존 로직 그대로, MVP 범위 밖 안내만 함)
- `programming_competency_certification.applies_to`: ["심화과정"], `topcit_min_score`: 190 (모든 원문에서 "심화과정 이수 시 필수" 계열 항목이라 동일하게 유지. 면제 조건 문구는 연도마다 약간 다르지만 — APC/SW전국대회 vs APC/Shake!/ACM-ICPC — 시스템이 이 문구를 계산에 쓰지 않고 화면에 그대로 노출만 하므로 모든 연도에 2025 문구를 그대로 재사용한다.)
- `industry_project_certification.course_groups`: 모든 학번 동일하게 6개 과목군(집중교육과목군에 **AI집중교육1,2 포함** — 사용자 지시: 21~24학번도 AI집중교육을 들으면 인증 과목군으로 인정) — Task 2에서 2021·2022 요람 원문엔 AI집중교육이 없어도 이 지시에 따라 전 학번에 동일하게 채운다.
  ```json
  {
    "집중교육과목군": ["IT집중교육1", "IT집중교육2", "AI집중교육1", "AI집중교육2"],
    "자기주도프로젝트과목군": ["자기주도프로젝트"],
    "현장실습과목군": ["SW현장실습1", "SW현장실습2", "SW현장실습3", "SW현장실습4", "SW현장실습5", "SW현장실습6"],
    "창업실습과목군": ["창업실습1", "창업실습2"],
    "캡스톤디자인과목군": ["SW캡스톤디자인"],
    "자기주도연구과목군": ["자기주도연구1", "자기주도연구2"]
  }
  ```

---

### Task 1: `app/audit.py` — 전공기초(major_foundation) 요건 추적 추가

**Files:**
- Modify: `app/audit.py:33-111` (AuditResult 데이터클래스 + audit_graduation 함수)
- Modify: `data/graduation_requirements.json:47-51`("2025" 항목에 `major_foundation_credit` 키 추가)
- Test: `tests/test_audit.py`

**Interfaces:**
- Consumes: 없음(기존 코드 확장)
- Produces: `AuditResult.major_foundation_credit_earned: int`(항상 계산, 요건이 없는 학번도 0 이상), `AuditResult.major_foundation_certified: bool | None`(그 학번에 `major_foundation_credit` 요건 자체가 없으면 `None` — "모른다"가 아니라 "해당 없음"). Task 2·5·7이 이 두 필드를 그대로 사용한다.

- [ ] **Step 1: 요건이 있는 학번(2025)에서 미달 시나리오로 실패하는 테스트 작성**

`tests/test_audit.py`에 `test_audit_industry_project_certified_with_two_courses_for_advanced_track` 함수 바로 앞에 추가:

```python
def test_audit_major_foundation_credit_tracked_when_year_has_the_requirement():
    # 2025학번은 전공기초 7학점(심화과정) 요건이 있다. SW커리어세미나(1)+확률및통계1(3)만
    # 이수하면 4학점으로 미달이어야 한다.
    transcript = TranscriptData(courses=[
        {"name": "SW커리어세미나", "credit": 1, "category": "전공기초"},
        {"name": "확률및통계1", "credit": 3, "category": "전공기초"},
    ])
    result = audit_graduation(transcript, admission_year=2025, track_type="심화과정",
                               requirements=load_requirements(2025))
    assert result.major_foundation_credit_earned == 4
    assert result.major_foundation_certified is False  # 7학점 기준, 4 < 7


def test_audit_major_foundation_certified_when_threshold_met():
    transcript = TranscriptData(courses=[
        {"name": "SW커리어세미나", "credit": 1, "category": "전공기초"},
        {"name": "확률및통계1", "credit": 3, "category": "전공기초"},
        {"name": "선형대수1", "credit": 3, "category": "전공기초"},
    ])
    result = audit_graduation(transcript, admission_year=2025, track_type="심화과정",
                               requirements=load_requirements(2025))
    assert result.major_foundation_credit_earned == 7
    assert result.major_foundation_certified is True


def test_audit_major_foundation_certified_is_none_when_year_has_no_such_requirement():
    # 21학번은 전공기초라는 요건 자체가 없다(교필로 찍혀 전공 학점 미인정) —
    # "미충족"이 아니라 "해당 없음"이어야 한다.
    transcript = TranscriptData(courses=[])
    result = audit_graduation(transcript, admission_year=2021, track_type="심화과정",
                               requirements=load_requirements(2021))
    assert result.major_foundation_certified is None
    assert result.major_foundation_credit_earned == 0
```

이 세 테스트는 아직 `load_requirements(2021)`이 없어서 `KeyError`가 나므로, 임시로 2021 항목을 최소한으로 먼저 넣지 않고 그대로 실패를 확인한다(Step 2).

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_audit.py -k major_foundation -v`
Expected: 세 테스트 모두 FAIL — 앞의 두 개는 `AttributeError: 'AuditResult' object has no attribute 'major_foundation_credit_earned'`, 세 번째는 `load_requirements`가 `KeyError: '2021'`을 던짐(아직 데이터 없음 — 이 테스트는 Task 2 완료 후에나 진짜로 GREEN이 된다. 지금은 앞의 두 개만 통과시키는 게 목표이므로, 세 번째 테스트는 `@pytest.mark.skip(reason="Task 2에서 2021 데이터 추가 후 활성화")`를 임시로 붙여둔다).

`tests/test_audit.py` 파일 최상단에 `import pytest` 추가하고, 세 번째 테스트 함수 위에 데코레이터를 붙인다:

```python
@pytest.mark.skip(reason="Task 2에서 2021 데이터 추가 후 활성화")
def test_audit_major_foundation_certified_is_none_when_year_has_no_such_requirement():
    ...
```

- [ ] **Step 3: `data/graduation_requirements.json`의 "2025" 항목에 `major_foundation_credit` 추가**

`data/graduation_requirements.json:47` (`"elective_major_credit"` 키) 바로 앞에 삽입:

```json
    "major_foundation_credit": {
      "심화과정": 7,
      "일반과정": 7,
      "복수과정": 6,
      "부전공": 6
    },
```

- [ ] **Step 4: `app/audit.py`에 필드·계산 로직 추가**

`app/audit.py:33-44`의 `AuditResult`를 다음으로 교체(새 필드 2개 추가, 기존 필드 순서·기본값 유지):

```python
@dataclass
class AuditResult:
    total_credit_earned: int
    required_major_completed: bool
    missing_required_major_courses: list[str]
    elective_major_credit_earned: int
    elective_major_certified: bool
    major_foundation_credit_earned: int
    major_foundation_certified: bool | None
    industry_project_certified: bool
    industry_project_count: int
    language_ok: bool | None
    unresolved: list[str] = field(default_factory=list)
    programming_competency_certified: bool | None = None  # Task 4-5가 자기신고로 채움(심화과정만 해당)
```

`app/audit.py:84-87`(`elective_courses = ...` 블록) 바로 뒤에 추가:

```python
    major_foundation_courses = [c for c in courses if c["category"] == "전공기초"]
    major_foundation_credit_earned = sum(c["credit"] for c in major_foundation_courses)
    major_foundation_threshold = requirements.get("major_foundation_credit", {}).get(track_type)
    major_foundation_certified = (
        None if major_foundation_threshold is None
        else major_foundation_credit_earned >= major_foundation_threshold
    )
```

`app/audit.py:101-111`의 `return AuditResult(...)` 블록에 두 인자 추가(`elective_major_certified=elective_major_certified,` 바로 뒤):

```python
        elective_major_certified=elective_major_certified,
        major_foundation_credit_earned=major_foundation_credit_earned,
        major_foundation_certified=major_foundation_certified,
```

- [ ] **Step 5: 테스트 실행해서 통과 확인 (skip은 아직 유지)**

Run: `.venv/bin/python -m pytest tests/test_audit.py -v`
Expected: 전부 PASS(3개 중 skip 표시된 1개 제외 2개 PASS), 다른 기존 테스트도 전부 그대로 PASS(새 필드가 위치 인자가 아니라 `AuditResult(**req.audit)`처럼 키워드로 생성되는 곳은 `app/api.py`의 `audit_selfreport`/`chat_answer` 핸들러뿐이고, 거긴 이미 딕셔너리 전개라 필드 추가에 자동 대응됨).

- [ ] **Step 6: 커밋**

```bash
git add app/audit.py data/graduation_requirements.json tests/test_audit.py
git commit -m "feat: 전공기초(major_foundation) 졸업요건 추적 추가"
```

---

### Task 2: `data/graduation_requirements.json` — 2021·2022·2023·2024·2026학번 데이터 추가

**Files:**
- Modify: `data/graduation_requirements.json`(파일 전체를 아래 최종본으로 교체)
- Test: `tests/test_audit.py`

**Interfaces:**
- Consumes: Task 1의 `AuditResult.major_foundation_credit_earned`/`major_foundation_certified`, `load_requirements(year)`(기존 시그니처 그대로, `app/audit.py:27-30`)
- Produces: `load_requirements(2021)`~`load_requirements(2026)` 전부 유효한 dict 반환. Task 4·5가 이 학번 범위를 그대로 신뢰하고 쓴다.

- [ ] **Step 1: Task 1에서 skip 처리한 테스트를 활성화하고, 학번별 핵심 시나리오 테스트를 추가로 작성**

`tests/test_audit.py`에서 방금 붙인 `@pytest.mark.skip(...)` 줄을 삭제한다(더는 필요 없음).

같은 파일 맨 끝에 추가:

```python
def test_audit_2021_uses_140_credit_and_36_credit_required_major_with_digital_circuit():
    # 21학번은 디지털회로가 전공필수에 포함되고(11개, 36학점), 창의소프트웨어입문을 쓴다.
    requirements = load_requirements(2021)
    assert requirements["total_credit"] == 140
    names = {c["name"] for c in requirements["required_major_courses"]}
    assert "디지털회로" in names
    assert "창의소프트웨어입문" in names
    assert "인공지능입문" not in names
    assert sum(c["credit"] for c in requirements["required_major_courses"]) == 36


def test_audit_2021_general_track_industry_project_fully_exempt():
    # 21학번 일반과정은 산학프로젝트 인증 자체가 면제 — 0과목이어도 충족이어야 한다.
    transcript = TranscriptData(courses=[])
    result = audit_graduation(transcript, admission_year=2021, track_type="일반과정",
                               requirements=load_requirements(2021))
    assert result.industry_project_count == 0
    assert result.industry_project_certified is True  # 0/0 = 면제


def test_audit_2021_general_track_elective_threshold_is_10_not_37():
    transcript = TranscriptData(courses=[
        {"name": "데이터베이스", "credit": 3, "category": "전공선택"},
        {"name": "정보보호", "credit": 3, "category": "전공선택"},
        {"name": "컴퓨터통신", "credit": 3, "category": "전공선택"},
    ])
    result = audit_graduation(transcript, admission_year=2021, track_type="일반과정",
                               requirements=load_requirements(2021))
    assert result.elective_major_credit_earned == 9
    assert result.elective_major_certified is False  # 9 < 10


def test_audit_2021_no_fieldwork_credit_cap():
    # 21학번은 현장실습 학점 상한이 없다 — 9학점 전부 인정돼야 한다(25+는 6학점 상한).
    transcript = TranscriptData(courses=[
        {"name": "SW현장실습1", "credit": 3, "category": "전공선택"},
        {"name": "SW현장실습2", "credit": 3, "category": "전공선택"},
        {"name": "SW현장실습3", "credit": 3, "category": "전공선택"},
    ])
    result = audit_graduation(transcript, admission_year=2021, track_type="일반과정",
                               requirements=load_requirements(2021))
    assert result.elective_major_credit_earned == 9  # 상한 없이 전부 인정


def test_audit_2022_identical_to_2021():
    requirements = load_requirements(2022)
    assert requirements == load_requirements(2021)


def test_audit_2023_uses_ai_intro_and_12_credit_fieldwork_cap():
    requirements = load_requirements(2023)
    names = {c["name"] for c in requirements["required_major_courses"]}
    assert "인공지능입문" in names
    assert "창의소프트웨어입문" not in names
    assert "디지털회로" in names
    assert requirements["elective_credit_cap_groups"]["현장실습군"]["max_credit"] == 12
    assert requirements["industry_project_certification"]["일반과정"]["min_courses"] == 1


def test_audit_2023_fieldwork_capped_at_12_not_6():
    transcript = TranscriptData(courses=[
        {"name": "SW현장실습1", "credit": 3, "category": "전공선택"},
        {"name": "SW현장실습2", "credit": 3, "category": "전공선택"},
        {"name": "SW현장실습3", "credit": 3, "category": "전공선택"},
        {"name": "SW현장실습4", "credit": 3, "category": "전공선택"},
        {"name": "SW현장실습5", "credit": 3, "category": "전공선택"},
    ])
    result = audit_graduation(transcript, admission_year=2023, track_type="일반과정",
                               requirements=load_requirements(2023))
    assert result.elective_major_credit_earned == 12  # 15학점 이수해도 12까지만 인정


def test_audit_2024_still_uses_140_credit_curriculum():
    requirements = load_requirements(2024)
    assert requirements["total_credit"] == 140


def test_audit_2026_required_major_drops_ai_intro_and_totals_29_credits():
    # 26학번은 인공지능입문이 전공필수에서 빠져 9개·29학점이 된다(25학번은 10개·32학점).
    requirements = load_requirements(2026)
    names = {c["name"] for c in requirements["required_major_courses"]}
    assert "인공지능입문" not in names
    assert "운영체제" in names
    assert len(requirements["required_major_courses"]) == 9
    assert sum(c["credit"] for c in requirements["required_major_courses"]) == 29
    assert requirements["total_credit"] == 128
    assert requirements["major_foundation_credit"]["심화과정"] == 7


def test_audit_all_years_share_the_same_industry_project_course_groups():
    # 사용자 지시: AI집중교육1,2는 21~26학번 전체에서 산학프로젝트 인증 과목군으로 인정.
    for year in [2021, 2022, 2023, 2024, 2025, 2026]:
        groups = load_requirements(year)["industry_project_certification"]["course_groups"]
        assert "AI집중교육1" in groups["집중교육과목군"]
        assert "AI집중교육2" in groups["집중교육과목군"]


def test_audit_all_years_share_the_identical_language_requirement():
    # 어학 기준은 학번별로 다른 게 아니라, TEPS/TOEIC Speaking만 신·구 버전을
    # 둘 다 인정하는 것뿐이다(2026-08-22 사용자 정정 — 학교 공식 어학 기준표 근거).
    reference = load_requirements(2021)["language_requirement"]
    for year in [2022, 2023, 2024, 2025, 2026]:
        assert load_requirements(year)["language_requirement"] == reference
    assert reference["TEPS"] == 605
    assert reference["TEPS_NEW"] == 329
    assert reference["TOEIC_Speaking_OLD"] == 5
    assert reference["TOEIC_Speaking"] == "IM1"
    assert reference["IELTS"] == 5.5
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_audit.py -v`
Expected: 새로 추가한 테스트 전부 FAIL(`KeyError: '2021'` 등, `load_requirements`가 해당 학번을 못 찾음). 기존 테스트는 그대로 PASS.

- [ ] **Step 3: `data/graduation_requirements.json`을 아래 최종본으로 전체 교체**

Task 1에서 이미 "2025"에 `major_foundation_credit`을 추가했으므로, 이번엔 파일 전체를 아래 내용으로 덮어쓴다(2025 항목은 Task 1 결과와 동일한 내용을 그대로 포함).

```json
{
  "2021": {
    "total_credit": 140,
    "min_gpa": 2.0,
    "required_major_courses": [
      { "name": "컴퓨터프로그래밍및실습", "credit": 4 },
      { "name": "이산수학", "credit": 3 },
      { "name": "창의소프트웨어입문", "credit": 3 },
      { "name": "디지털회로", "credit": 3 },
      { "name": "객체지향프로그래밍및실습", "credit": 4 },
      { "name": "자료구조", "credit": 3 },
      { "name": "컴퓨터구조", "credit": 3 },
      { "name": "알고리즘", "credit": 3 },
      { "name": "시스템프로그래밍및실습", "credit": 4 },
      { "name": "컴퓨터네트워크", "credit": 3 },
      { "name": "운영체제", "credit": 3 }
    ],
    "elective_major_credit": { "심화과정": 37, "일반과정": 10, "복수과정": 10 },
    "requires_double_major_or_minor": ["일반과정", "복수과정"],
    "industry_project_certification": {
      "심화과정": { "min_courses": 2 },
      "일반과정": { "min_courses": 0 },
      "복수과정": { "min_courses": 0 },
      "course_groups": {
        "집중교육과목군": ["IT집중교육1", "IT집중교육2", "AI집중교육1", "AI집중교육2"],
        "자기주도프로젝트과목군": ["자기주도프로젝트"],
        "현장실습과목군": ["SW현장실습1", "SW현장실습2", "SW현장실습3", "SW현장실습4", "SW현장실습5", "SW현장실습6"],
        "창업실습과목군": ["창업실습1", "창업실습2"],
        "캡스톤디자인과목군": ["SW캡스톤디자인"],
        "자기주도연구과목군": ["자기주도연구1", "자기주도연구2"]
      }
    },
    "programming_competency_certification": {
      "applies_to": ["심화과정"],
      "topcit_min_score": 190,
      "exemptions": [
        "APC 대회 참가 및 1문제 이상 정답",
        "SW 관련 전국대회 입상(2개년 이상 개최, 참가 100명 이상)"
      ]
    },
    "language_requirement": {
      "TOEIC": 730, "TEPS": 605, "TEPS_NEW": 329, "TOEFL_PBT": 534, "TOEFL_CBT": 200,
      "TOEFL_iBT": 72, "GTELP_Lv2": 67, "GTELP_Lv3": 89, "TOEIC_Speaking_OLD": 5,
      "TOEIC_Speaking": "IM1", "OPIc": "IL", "IELTS": 5.5
    }
  },
  "2022": {
    "total_credit": 140,
    "min_gpa": 2.0,
    "required_major_courses": [
      { "name": "컴퓨터프로그래밍및실습", "credit": 4 },
      { "name": "이산수학", "credit": 3 },
      { "name": "창의소프트웨어입문", "credit": 3 },
      { "name": "디지털회로", "credit": 3 },
      { "name": "객체지향프로그래밍및실습", "credit": 4 },
      { "name": "자료구조", "credit": 3 },
      { "name": "컴퓨터구조", "credit": 3 },
      { "name": "알고리즘", "credit": 3 },
      { "name": "시스템프로그래밍및실습", "credit": 4 },
      { "name": "컴퓨터네트워크", "credit": 3 },
      { "name": "운영체제", "credit": 3 }
    ],
    "elective_major_credit": { "심화과정": 37, "일반과정": 10, "복수과정": 10 },
    "requires_double_major_or_minor": ["일반과정", "복수과정"],
    "industry_project_certification": {
      "심화과정": { "min_courses": 2 },
      "일반과정": { "min_courses": 0 },
      "복수과정": { "min_courses": 0 },
      "course_groups": {
        "집중교육과목군": ["IT집중교육1", "IT집중교육2", "AI집중교육1", "AI집중교육2"],
        "자기주도프로젝트과목군": ["자기주도프로젝트"],
        "현장실습과목군": ["SW현장실습1", "SW현장실습2", "SW현장실습3", "SW현장실습4", "SW현장실습5", "SW현장실습6"],
        "창업실습과목군": ["창업실습1", "창업실습2"],
        "캡스톤디자인과목군": ["SW캡스톤디자인"],
        "자기주도연구과목군": ["자기주도연구1", "자기주도연구2"]
      }
    },
    "programming_competency_certification": {
      "applies_to": ["심화과정"],
      "topcit_min_score": 190,
      "exemptions": [
        "APC 대회 참가 및 1문제 이상 정답",
        "SW 관련 전국대회 입상(2개년 이상 개최, 참가 100명 이상)"
      ]
    },
    "language_requirement": {
      "TOEIC": 730, "TEPS": 605, "TEPS_NEW": 329, "TOEFL_PBT": 534, "TOEFL_CBT": 200,
      "TOEFL_iBT": 72, "GTELP_Lv2": 67, "GTELP_Lv3": 89, "TOEIC_Speaking_OLD": 5,
      "TOEIC_Speaking": "IM1", "OPIc": "IL", "IELTS": 5.5
    }
  },
  "2023": {
    "total_credit": 140,
    "min_gpa": 2.0,
    "required_major_courses": [
      { "name": "컴퓨터프로그래밍및실습", "credit": 4 },
      { "name": "이산수학", "credit": 3 },
      { "name": "인공지능입문", "credit": 3 },
      { "name": "디지털회로", "credit": 3 },
      { "name": "객체지향프로그래밍및실습", "credit": 4 },
      { "name": "자료구조", "credit": 3 },
      { "name": "컴퓨터구조", "credit": 3 },
      { "name": "알고리즘", "credit": 3 },
      { "name": "시스템프로그래밍및실습", "credit": 4 },
      { "name": "컴퓨터네트워크", "credit": 3 },
      { "name": "운영체제", "credit": 3 }
    ],
    "elective_major_credit": { "심화과정": 37, "일반과정": 10, "복수과정": 10 },
    "elective_credit_cap_groups": {
      "현장실습군": {
        "courses": [
          "SW현장실습1", "SW현장실습2", "SW현장실습3", "SW현장실습4", "SW현장실습5", "SW현장실습6",
          "창업실습1", "창업실습2", "창업현장실습1", "창업현장실습2"
        ],
        "max_credit": 12
      }
    },
    "requires_double_major_or_minor": ["일반과정", "복수과정"],
    "industry_project_certification": {
      "심화과정": { "min_courses": 2 },
      "일반과정": { "min_courses": 1 },
      "복수과정": { "min_courses": 1 },
      "course_groups": {
        "집중교육과목군": ["IT집중교육1", "IT집중교육2", "AI집중교육1", "AI집중교육2"],
        "자기주도프로젝트과목군": ["자기주도프로젝트"],
        "현장실습과목군": ["SW현장실습1", "SW현장실습2", "SW현장실습3", "SW현장실습4", "SW현장실습5", "SW현장실습6"],
        "창업실습과목군": ["창업실습1", "창업실습2"],
        "캡스톤디자인과목군": ["SW캡스톤디자인"],
        "자기주도연구과목군": ["자기주도연구1", "자기주도연구2"]
      }
    },
    "programming_competency_certification": {
      "applies_to": ["심화과정"],
      "topcit_min_score": 190,
      "exemptions": [
        "APC 대회 참가 및 1문제 이상 정답",
        "SW 관련 전국대회 입상(2개년 이상 개최, 참가 100명 이상)"
      ]
    },
    "language_requirement": {
      "TOEIC": 730, "TEPS": 605, "TEPS_NEW": 329, "TOEFL_PBT": 534, "TOEFL_CBT": 200,
      "TOEFL_iBT": 72, "GTELP_Lv2": 67, "GTELP_Lv3": 89, "TOEIC_Speaking_OLD": 5,
      "TOEIC_Speaking": "IM1", "OPIc": "IL", "IELTS": 5.5
    }
  },
  "2024": {
    "total_credit": 140,
    "min_gpa": 2.0,
    "required_major_courses": [
      { "name": "컴퓨터프로그래밍및실습", "credit": 4 },
      { "name": "이산수학", "credit": 3 },
      { "name": "인공지능입문", "credit": 3 },
      { "name": "디지털회로", "credit": 3 },
      { "name": "객체지향프로그래밍및실습", "credit": 4 },
      { "name": "자료구조", "credit": 3 },
      { "name": "컴퓨터구조", "credit": 3 },
      { "name": "알고리즘", "credit": 3 },
      { "name": "시스템프로그래밍및실습", "credit": 4 },
      { "name": "컴퓨터네트워크", "credit": 3 },
      { "name": "운영체제", "credit": 3 }
    ],
    "elective_major_credit": { "심화과정": 37, "일반과정": 10, "복수과정": 10 },
    "elective_credit_cap_groups": {
      "현장실습군": {
        "courses": [
          "SW현장실습1", "SW현장실습2", "SW현장실습3", "SW현장실습4", "SW현장실습5", "SW현장실습6",
          "창업실습1", "창업실습2", "창업현장실습1", "창업현장실습2"
        ],
        "max_credit": 12
      }
    },
    "requires_double_major_or_minor": ["일반과정", "복수과정"],
    "industry_project_certification": {
      "심화과정": { "min_courses": 2 },
      "일반과정": { "min_courses": 1 },
      "복수과정": { "min_courses": 1 },
      "course_groups": {
        "집중교육과목군": ["IT집중교육1", "IT집중교육2", "AI집중교육1", "AI집중교육2"],
        "자기주도프로젝트과목군": ["자기주도프로젝트"],
        "현장실습과목군": ["SW현장실습1", "SW현장실습2", "SW현장실습3", "SW현장실습4", "SW현장실습5", "SW현장실습6"],
        "창업실습과목군": ["창업실습1", "창업실습2"],
        "캡스톤디자인과목군": ["SW캡스톤디자인"],
        "자기주도연구과목군": ["자기주도연구1", "자기주도연구2"]
      }
    },
    "programming_competency_certification": {
      "applies_to": ["심화과정"],
      "topcit_min_score": 190,
      "exemptions": [
        "APC 대회 참가 및 1문제 이상 정답",
        "SW 관련 전국대회 입상(2개년 이상 개최, 참가 100명 이상)"
      ]
    },
    "language_requirement": {
      "TOEIC": 730, "TEPS": 605, "TEPS_NEW": 329, "TOEFL_PBT": 534, "TOEFL_CBT": 200,
      "TOEFL_iBT": 72, "GTELP_Lv2": 67, "GTELP_Lv3": 89, "TOEIC_Speaking_OLD": 5,
      "TOEIC_Speaking": "IM1", "OPIc": "IL", "IELTS": 5.5
    }
  },
  "2025": {
    "total_credit": 128,
    "min_gpa": 2.0,
    "required_major_courses": [
      { "name": "컴퓨터프로그래밍및실습", "credit": 4 },
      { "name": "이산수학", "credit": 3 },
      { "name": "인공지능입문", "credit": 3 },
      { "name": "객체지향프로그래밍및실습", "credit": 4 },
      { "name": "자료구조", "credit": 3 },
      { "name": "컴퓨터구조", "credit": 3 },
      { "name": "알고리즘", "credit": 3 },
      { "name": "컴퓨터네트워크", "credit": 3 },
      { "name": "운영체제", "credit": 3 },
      { "name": "시스템프로그래밍", "credit": 3 }
    ],
    "major_foundation_credit": { "심화과정": 7, "일반과정": 7, "복수과정": 6, "부전공": 6 },
    "elective_major_credit": { "심화과정": 32, "일반과정": 10, "복수과정": 10 },
    "elective_credit_cap_groups": {
      "현장실습군": {
        "courses": [
          "SW현장실습1", "SW현장실습2", "SW현장실습3", "SW현장실습4", "SW현장실습5", "SW현장실습6",
          "창업실습1", "창업실습2", "창업현장실습1", "창업현장실습2"
        ],
        "max_credit": 6
      }
    },
    "requires_double_major_or_minor": ["일반과정", "복수과정"],
    "industry_project_certification": {
      "심화과정": { "min_courses": 2 },
      "일반과정": { "min_courses": 1 },
      "복수과정": { "min_courses": 1 },
      "course_groups": {
        "집중교육과목군": ["IT집중교육1", "IT집중교육2", "AI집중교육1", "AI집중교육2"],
        "자기주도프로젝트과목군": ["자기주도프로젝트"],
        "현장실습과목군": ["SW현장실습1", "SW현장실습2", "SW현장실습3", "SW현장실습4", "SW현장실습5", "SW현장실습6"],
        "창업실습과목군": ["창업실습1", "창업실습2"],
        "캡스톤디자인과목군": ["SW캡스톤디자인"],
        "자기주도연구과목군": ["자기주도연구1", "자기주도연구2"]
      }
    },
    "programming_competency_certification": {
      "applies_to": ["심화과정"],
      "topcit_min_score": 190,
      "exemptions": [
        "APC 대회 참가 및 1문제 이상 정답",
        "SW 관련 전국대회 입상(2개년 이상 개최, 참가 100명 이상)"
      ]
    },
    "language_requirement": {
      "TOEIC": 730, "TEPS": 605, "TEPS_NEW": 329, "TOEFL_PBT": 534, "TOEFL_CBT": 200,
      "TOEFL_iBT": 72, "GTELP_Lv2": 67, "GTELP_Lv3": 89, "TOEIC_Speaking_OLD": 5,
      "TOEIC_Speaking": "IM1", "OPIc": "IL", "IELTS": 5.5
    }
  },
  "2026": {
    "total_credit": 128,
    "min_gpa": 2.0,
    "required_major_courses": [
      { "name": "컴퓨터프로그래밍및실습", "credit": 4 },
      { "name": "이산수학", "credit": 3 },
      { "name": "객체지향프로그래밍및실습", "credit": 4 },
      { "name": "자료구조", "credit": 3 },
      { "name": "컴퓨터구조", "credit": 3 },
      { "name": "알고리즘", "credit": 3 },
      { "name": "컴퓨터네트워크", "credit": 3 },
      { "name": "시스템프로그래밍", "credit": 3 },
      { "name": "운영체제", "credit": 3 }
    ],
    "major_foundation_credit": { "심화과정": 7, "일반과정": 7, "복수과정": 6, "부전공": 6 },
    "elective_major_credit": { "심화과정": 32, "일반과정": 10, "복수과정": 10 },
    "elective_credit_cap_groups": {
      "현장실습군": {
        "courses": [
          "SW현장실습1", "SW현장실습2", "SW현장실습3", "SW현장실습4", "SW현장실습5", "SW현장실습6",
          "창업실습1", "창업실습2", "창업현장실습1", "창업현장실습2"
        ],
        "max_credit": 6
      }
    },
    "requires_double_major_or_minor": ["일반과정", "복수과정"],
    "industry_project_certification": {
      "심화과정": { "min_courses": 2 },
      "일반과정": { "min_courses": 1 },
      "복수과정": { "min_courses": 1 },
      "course_groups": {
        "집중교육과목군": ["IT집중교육1", "IT집중교육2", "AI집중교육1", "AI집중교육2"],
        "자기주도프로젝트과목군": ["자기주도프로젝트"],
        "현장실습과목군": ["SW현장실습1", "SW현장실습2", "SW현장실습3", "SW현장실습4", "SW현장실습5", "SW현장실습6"],
        "창업실습과목군": ["창업실습1", "창업실습2"],
        "캡스톤디자인과목군": ["SW캡스톤디자인"],
        "자기주도연구과목군": ["자기주도연구1", "자기주도연구2"]
      }
    },
    "programming_competency_certification": {
      "applies_to": ["심화과정"],
      "topcit_min_score": 190,
      "exemptions": [
        "APC 대회 참가 및 1문제 이상 정답",
        "SW 관련 전국대회 입상(2개년 이상 개최, 참가 100명 이상)"
      ]
    },
    "language_requirement": {
      "TOEIC": 730, "TEPS": 605, "TEPS_NEW": 329, "TOEFL_PBT": 534, "TOEFL_CBT": 200,
      "TOEFL_iBT": 72, "GTELP_Lv2": 67, "GTELP_Lv3": 89, "TOEIC_Speaking_OLD": 5,
      "TOEIC_Speaking": "IM1", "OPIc": "IL", "IELTS": 5.5
    }
  }
}
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_audit.py -v`
Expected: 전부 PASS (기존 테스트 포함, Task 1의 3개 테스트 포함).

Run: `.venv/bin/python -m pytest -q`
Expected: 전체 스위트 그대로 PASS(다른 파일에 영향 없음 — `load_requirements`/`audit_graduation` 시그니처 불변, 새 학번 키만 추가됐을 뿐).

- [ ] **Step 5: 커밋**

```bash
git add data/graduation_requirements.json tests/test_audit.py
git commit -m "feat: 21~24·26학번 졸업요건 데이터 추가(요람 원문 대조 완료)"
```

---

### Task 3: `app/llm.py` — 이수구분 약어 매핑 + 전공기초 카테고리 + 수강년도 추출

**Files:**
- Modify: `app/llm.py:16-23`(`PROMPT_TEMPLATE`)
- Test: `tests/test_llm.py`

**Interfaces:**
- Consumes: 없음
- Produces: `PROMPT_TEMPLATE`이 요구하는 과목 JSON 스키마가 `{"name": str, "credit": number, "category": str, "year": int}`으로 확장됨(`category`는 "전공필수"|"전공선택"|"전공기초"|"교양필수"|"교양선택"|"일반선택" 중 하나). Task 4가 이 `"year"` 필드를 읽는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_llm.py`에서 기존 `test_prompt_template_category_enum_includes_major_foundation` 테스트를 다음으로 교체(같은 함수명 유지, 내용 확장):

```python
def test_prompt_template_category_enum_includes_major_foundation():
    # 요람상 전공기초(확률및통계1, SW커리어세미나 등)는 전공필수/전공선택과 별도
    # 영역인데, 프롬프트가 이 카테고리를 몰라 LLM이 "전공선택"으로 잘못 분류했다
    # (2026-08-22 실사용 버그 리포트).
    assert "전공기초" in PROMPT_TEMPLATE


def test_prompt_template_maps_transcript_abbreviations_to_full_category_names():
    # 실제 아주대 성적표는 이수구분이 "전필/전선/전기/교필/교선/일선" 약어로 찍혀
    # 있다(성적표.pdf 실측 확인, 2026-08-22). 특히 "전기"는 "전기공학"과 혼동되기
    # 쉬워 프롬프트에 명시적으로 매핑을 알려줘야 한다.
    for abbr in ["전필", "전선", "전기", "교필", "교선", "일선"]:
        assert abbr in PROMPT_TEMPLATE
    assert "전기공학" in PROMPT_TEMPLATE  # 혼동하지 말라는 경고 문구가 있어야 함
    assert "일반선택" in PROMPT_TEMPLATE  # "일선" 대응 카테고리, 기존 enum엔 없었음


def test_prompt_template_requires_year_field_for_admission_year_inference():
    # 학번(admission_year)은 화면 입력이 아니라 성적표의 "수강년도" 최솟값으로
    # 서버가 자동 추론한다(1학년 1학기 휴학 불가 교칙 근거, 2026-08-22 사용자 지시).
    # 그러려면 과목마다 수강년도를 추출해야 한다.
    assert "year" in PROMPT_TEMPLATE
    assert "수강년도" in PROMPT_TEMPLATE
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_llm.py -k "abbreviat or year_field" -v`
Expected: 두 개 다 FAIL(`assert '전필' in PROMPT_TEMPLATE` 등에서 AssertionError).

- [ ] **Step 3: `PROMPT_TEMPLATE` 교체**

`app/llm.py:16-23`을 다음으로 교체:

```python
PROMPT_TEMPLATE = """다음은 마스킹된 대학교 성적표 텍스트다. 이수한 과목만 골라
JSON 배열로 출력하라. 각 항목은 {{"name": 과목명, "credit": 학점(숫자),
"category": 이수구분, "year": 수강년도(4자리 정수)}} 형태여야 한다.

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
year는 2021). 수강년도가 없는 행은 통째로 건너뛰어라.

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
git commit -m "feat: 성적표 이수구분 약어 매핑 + 전공기초 카테고리 + 수강년도 추출"
```

---

### Task 4: `app/parser.py` — 성적표에서 입학년도 자동 추론

**Files:**
- Modify: `app/parser.py`
- Test: `tests/test_parser.py`

**Interfaces:**
- Consumes: 없음
- Produces: `infer_admission_year(courses: list[dict]) -> int | None` — `courses`는 각 항목이 `"year"` 키(있을 수도 없을 수도 있음, Task 3의 LLM 출력 또는 개발 모드 수동 입력이라 신뢰 못 함)를 가진 dict 리스트. 최솟값을 반환하고, `"year"`가 있는 과목이 하나도 없으면 `None`. Task 5가 이 함수를 가져다 쓴다(`from app.parser import infer_admission_year`).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_parser.py` 맨 끝에 추가:

```python
from app.parser import infer_admission_year


def test_infer_admission_year_returns_minimum_year_across_courses():
    # 1학년 1학기 휴학은 교칙상 불가능하므로, 성적표에 찍힌 수강년도의 최솟값이
    # 곧 입학년도다(2026-08-22 사용자 지시).
    courses = [
        {"name": "선형대수1", "credit": 3, "category": "전공기초", "year": 2025},
        {"name": "SW커리어세미나", "credit": 1, "category": "전공기초", "year": 2021},
        {"name": "이산수학", "credit": 3, "category": "전공필수", "year": 2021},
    ]
    assert infer_admission_year(courses) == 2021


def test_infer_admission_year_returns_none_when_no_course_has_year():
    # 개발 모드(GOOGLE_API_KEY 없음)에서 사용자가 과목을 직접 입력하면 year가
    # 없을 수 있다 — 이땐 "모른다"를 그대로 알려야 한다(추측해서 채우지 않는다).
    courses = [{"name": "자료구조", "credit": 3, "category": "전공필수"}]
    assert infer_admission_year(courses) is None


def test_infer_admission_year_ignores_courses_missing_year_field():
    courses = [
        {"name": "자료구조", "credit": 3, "category": "전공필수", "year": 2022},
        {"name": "수동입력과목", "credit": 3, "category": "전공선택"},  # year 없음
    ]
    assert infer_admission_year(courses) == 2022


def test_infer_admission_year_returns_none_for_empty_course_list():
    assert infer_admission_year([]) is None
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_parser.py -k infer_admission_year -v`
Expected: 전부 FAIL — `ImportError: cannot import name 'infer_admission_year' from 'app.parser'`.

- [ ] **Step 3: 함수 구현**

`app/parser.py`의 `TranscriptData` 데이터클래스 정의(`class TranscriptData:` 블록) 바로 뒤, `def extract_words_from_pdf` 앞에 추가:

```python
def infer_admission_year(courses: list[dict]) -> int | None:
    """1학년 1학기는 휴학이 교칙상 불가능하므로, 성적표에 찍힌 "수강년도"(courses의
    "year" 키) 중 최솟값이 곧 입학년도다. 사용자가 화면에서 입학년도를 직접 입력하지
    않아도 되게 하려고 서버가 자동으로 추론한다(2026-08-22 사용자 지시). "year"가
    있는 과목이 하나도 없으면(예: 개발 모드 수동 입력) 추측하지 않고 None을 돌려준다."""
    years = [c["year"] for c in courses if "year" in c]
    return min(years) if years else None
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_parser.py -v`
Expected: 전부 PASS.

- [ ] **Step 5: 커밋**

```bash
git add app/parser.py tests/test_parser.py
git commit -m "feat: 성적표 수강년도 최솟값으로 입학년도 자동 추론"
```

---

### Task 5: `app/api.py` — 입학년도 자동 추론을 업로드/플랜 파이프라인에 연결

**Files:**
- Modify: `app/api.py:133-161`(`/api/upload`), `app/api.py:241-314`(`/api/plan`)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `infer_admission_year` (Task 4, `app/parser.py`)
- Produces: `/api/upload` 응답에 `"admission_year": int | None` 추가. `/api/plan` 응답에 `"admission_year": int` 추가(실제로 판정에 쓰인 값 — 프론트가 이 값을 신뢰해서 저장). `PlanRequest.admission_year`는 **삭제하지 않는다** — courses에 `"year"`가 하나도 없을 때(개발 모드 수동 입력 등) 쓸 폴백이다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_api.py`에서 `def test_upload_masks_pii_and_returns_courses_without_api_key(monkeypatch):` 함수 뒤에 추가:

```python
def test_upload_includes_inferred_admission_year_in_response(monkeypatch):
    from app.masking import mask_and_validate

    monkeypatch.setattr(
        "app.api.parse_transcript",
        lambda pdf_bytes, structure_fn: TranscriptData(
            courses=[
                {"name": "이산수학", "credit": 3, "category": "전공필수", "year": 2022},
                {"name": "자료구조", "credit": 3, "category": "전공필수", "year": 2023},
            ],
            masked_text="dummy",
        ),
    )
    res = client.post("/api/upload", files={"file": ("t.pdf", b"%PDF-1.4", "application/pdf")})
    assert res.status_code == 200
    assert res.json()["admission_year"] == 2022


def test_plan_infers_admission_year_from_courses_year_field_over_request_default():
    # req.admission_year는 기본값 2025지만, courses가 2021년도 수강 기록을 담고
    # 있으면 서버는 그쪽을 신뢰해 2021학번 요건(140학점)으로 판정해야 한다.
    payload = {
        "courses": [
            {"name": "이산수학", "credit": 3, "category": "전공필수", "year": 2021},
        ],
        "admission_year": 2025,
        "track_type": "심화과정", "track": "백엔드",
    }
    res = client.post("/api/plan", json=payload)
    body = res.json()
    assert body["admission_year"] == 2021
    assert body["requirements_summary"]["total_credit_required"] == 140  # 2021학번 기준


def test_plan_falls_back_to_request_admission_year_when_courses_lack_year(monkeypatch):
    # courses에 year가 하나도 없으면(개발 모드 수동 입력 등) req.admission_year를
    # 그대로 쓴다 — 기존 동작과 100% 호환.
    payload = {
        "courses": [], "admission_year": 2025, "track_type": "심화과정", "track": "백엔드",
    }
    res = client.post("/api/plan", json=payload)
    body = res.json()
    assert body["admission_year"] == 2025
    assert body["requirements_summary"]["total_credit_required"] == 128
```

`tests/test_api.py` 최상단에 `TranscriptData` import가 없으면 추가:

```python
from app.parser import TranscriptData
```
(이미 import돼 있다면 생략 — 파일 상단을 먼저 확인할 것.)

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_api.py -k "admission_year" -v`
Expected: 새로 추가한 3개 테스트 모두 FAIL(`KeyError: 'admission_year'` — 아직 응답에 그 키가 없음).

- [ ] **Step 3: `/api/upload` 핸들러 수정**

`app/api.py:14-16`의 import 블록에서 `from app.parser import InjectionDetected, TranscriptData, parse_transcript`를 다음으로 교체:

```python
from app.parser import InjectionDetected, TranscriptData, infer_admission_year, parse_transcript
```

`app/api.py:151-155`의 `response = {...}` 블록을 다음으로 교체:

```python
    response = {
        "courses": transcript.courses,
        "pii_masked": True,
        "masked_preview": transcript.masked_text[:1200],
        "admission_year": infer_admission_year(transcript.courses),
    }
```

- [ ] **Step 4: `/api/plan` 핸들러 수정**

`app/api.py:241-246`(`@app.post("/api/plan")` 함수 시작 부분)을 다음으로 교체:

```python
@app.post("/api/plan")
def plan(req: PlanRequest):
    resolved_admission_year = infer_admission_year(req.courses) or req.admission_year
    transcript = TranscriptData(courses=req.courses)
    requirements = load_requirements(resolved_admission_year)
    audit = audit_graduation(transcript, resolved_admission_year, req.track_type, requirements)
    audit = _apply_dropdown_selfreports(audit, req, requirements)
```

이 함수 안에서 이후 `req.admission_year`를 참조하는 곳은 없다(재확인: `load_requirements`/`audit_graduation` 호출은 이미 위에서 `resolved_admission_year`로 바뀜). `app/api.py:296-309`의 `response = {...}` 블록에 `"admission_year": resolved_admission_year,`를 `"audit": asdict(audit),` 바로 뒤에 추가:

```python
    response = {
        "audit": asdict(audit),
        "admission_year": resolved_admission_year,
        "requirements_summary": requirements_summary,
        ...
```

- [ ] **Step 5: 테스트 실행해서 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_api.py -v`
Expected: 전부 PASS(기존 30여 개 `admission_year: 2025` 호출부는 여전히 `courses`에 `year`가 없는 시나리오라 폴백 경로를 타서 그대로 통과한다).

Run: `.venv/bin/python -m pytest -q`
Expected: 전체 스위트 PASS.

- [ ] **Step 6: 커밋**

```bash
git add app/api.py tests/test_api.py
git commit -m "feat: /api/upload·/api/plan이 성적표에서 입학년도를 자동 추론"
```

---

### Task 6: `app/static/js/upload.js` — 화면에 실제 추론된 입학년도 반영

**Files:**
- Modify: `app/static/js/upload.js:12`(변수 선언), `app/static/js/upload.js:104-126`(업로드 응답 처리), `app/static/js/upload.js:426-437`(플랜 제출)
- Modify: `app/static/upload.html:116-119`("대상 학번" 잠금 칩)

**Interfaces:**
- Consumes: Task 5의 `/api/upload` 응답 `body.admission_year`, `/api/plan` 응답 `result.admission_year`
- Produces: `sessionStorage`의 `pathfinder:formState`에 저장되는 `admission_year`가 서버가 실제로 판정에 쓴 값과 일치함. `app/static/js/dashboard.js:123`의 `${FORM_STATE.admission_year}학년도 학사요람` 표시가 이제 정확해진다(코드 변경 불필요 — 이미 `FORM_STATE.admission_year`를 그대로 읽고 있음). 화면1의 "대상 학번" 잠금 칩도 하드코딩된 "2025학번" 대신 실제 감지된 학번을 보여준다.

**주의:** `app/static/upload.html:118`에 지금 `<div class="locked-chip">2025학번 · 소프트웨어학과</div>`가 하드코딩돼 있다 — 21~26학번 확장 이후엔 이게 거짓 정보가 된다(모든 사용자에게 "2025학번"이라고 잘못 표시). 파일을 업로드하면 그 시점에 서버가 이미 학번을 추론할 수 있으므로(Task 5의 `/api/upload` 응답), 업로드 직후 이 칩 텍스트를 실제 값으로 갱신한다.

- [ ] **Step 1: 브라우저로 재현해서 현재 버그 확인**

로컬 서버가 이미 떠 있다면(`http://127.0.0.1:8000`), 헤드리스 브라우저로 아래를 실행해 현재는 `pathfinder:formState.admission_year`가 항상 2025로 저장됨을 확인한다(수정 전 baseline):

```bash
SCRATCH="/private/tmp/claude-501/-Users-minwoo-Documents-Study-AI------2------/600265f2-a15e-4a4d-bfbc-4fd9b26db127/scratchpad"
# 기존 cdp.js 패턴을 참고해 upload.html -> handleSubmit 흐름을 재현하는 스크립트를
# 짧게 작성해 pathfinder:formState.admission_year 값을 확인한다.
```
(자동화 스크립트를 새로 짤 필요 없이, Step 2 코드 변경 후 Task 7과 함께 한 번에 브라우저 검증해도 된다 — 이 Step은 문제 존재를 코드로 재확인하는 용도이므로 시간이 빠듯하면 Step 2로 바로 넘어가도 무방하다.)

- [ ] **Step 2: "대상 학번" 잠금 칩을 하드코딩에서 동적 표시로 변경**

`app/static/upload.html:118`을 다음으로 교체:

```html
            <div class="locked-chip" id="admissionYearChip">학번 확인 중 · 소프트웨어학과</div>
```

`app/static/js/upload.js:12`(`let uploadedCourses = [];`) 바로 뒤에 변수 추가:

```javascript
let detectedAdmissionYear = null;
```

`app/static/js/upload.js:123`(`uploadedCourses = body.courses || [];`) 바로 뒤에 추가:

```javascript
    detectedAdmissionYear = body.admission_year || null;
    const chip = document.getElementById("admissionYearChip");
    chip.textContent = detectedAdmissionYear
      ? `${detectedAdmissionYear}학번 · 소프트웨어학과`
      : "학번 확인 불가 · 소프트웨어학과"; // 개발 모드(과목 미인식) 등 수강년도를 못 얻은 경우
```

- [ ] **Step 3: `/api/plan` 제출 시 실제 판정에 쓰인 입학년도로 formState 갱신**

`app/static/js/upload.js:426-436`을 다음으로 교체:

```javascript
  try {
    const res = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const result = await res.json();

    // 서버가 성적표의 수강년도로 실제 판정에 쓴 입학년도를 되돌려준다 — 화면1에서
    // 보낸 admission_year(기본값 2025)는 폴백일 뿐이라, 응답값으로 덮어써야
    // 대시보드의 "OOOO학년도 학사요람" 표시와 자기신고 재판정이 정확해진다
    // (2026-08-22, 21~26학번 확장).
    if (result.admission_year) {
      payload.admission_year = result.admission_year;
    }

    sessionStorage.setItem("pathfinder:formState", JSON.stringify(payload));
    sessionStorage.setItem("pathfinder:planResult", JSON.stringify(result));
    window.location.href = "dashboard.html"; // 페이지 이동으로 오버레이도 자연히 사라짐
```

(마지막 줄 `window.location.href = ...`은 기존 코드 그대로이므로 그 아래 이어지는 나머지 코드는 손대지 않는다.)

- [ ] **Step 4: 헤드리스 브라우저로 검증**

```bash
SCRATCH="/private/tmp/claude-501/-Users-minwoo-Documents-Study-AI------2------/600265f2-a15e-4a4d-bfbc-4fd9b26db127/scratchpad"
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --remote-debugging-port=9333 --no-first-run --no-default-browser-check \
  --disable-gpu --user-data-dir="$SCRATCH/chrome-profile-verify2" \
  > "$SCRATCH/chrome_verify2.log" 2>&1 &
disown
sleep 2
```

`$SCRATCH/cdp_admission_year.js`를 새로 작성해(기존 `cdp.js` 패턴 참고) 두 가지를 확인한다:
1. `upload.html`을 로드하고 `body.admission_year`를 포함한 `/api/upload` 응답을 흉내 내는 대신, `uploadedCourses`와 `detectedAdmissionYear`를 직접 주입한 뒤 `document.getElementById("admissionYearChip").textContent`가 `"2021학번 · 소프트웨어학과"` 형태인지 확인.
2. `uploadedCourses`에 `year` 필드가 있는 과목을 주입하고 `handleSubmit`을 트리거한 뒤 `sessionStorage.getItem("pathfinder:formState")`의 `admission_year`를 확인.

서버(`uvicorn`)가 로컬에서 이미 떠 있어야 한다(`lsof -i :8000`으로 확인, 없으면 `python serve.py` 또는 프로젝트의 기존 실행 방법으로 띄운다).

Expected: 잠금 칩이 실제 감지된 학번을 보여주고, `admission_year`가 주입한 과목의 최솟값 `year`와 일치.

- [ ] **Step 5: 커밋**

```bash
git add app/static/js/upload.js app/static/upload.html
git commit -m "fix: 대시보드·업로드 화면에 서버가 추론한 실제 입학년도를 반영"
```

---

### Task 7: 전공기초 요건을 졸업 현황 카드에 표시

**Files:**
- Modify: `app/api.py:266-276`(`requirements_summary` 블록)
- Modify: `app/static/js/dashboard.js:58-96`(`renderCreditCard`)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: Task 1의 `AuditResult.major_foundation_credit_earned`/`major_foundation_certified`
- Produces: `/api/plan` 응답의 `requirements_summary.major_foundation_credit_required`(그 학번에 요건이 없으면 키 자체가 없음 — `undefined`). `dashboard.js`가 이 키의 존재 여부로 카드에 "전공기초" 항목을 보여줄지 결정한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_api.py`에 추가:

```python
def test_plan_requirements_summary_includes_major_foundation_credit_for_2025():
    payload = {
        "courses": [], "admission_year": 2025, "track_type": "심화과정", "track": "백엔드",
    }
    res = client.post("/api/plan", json=payload)
    assert res.json()["requirements_summary"]["major_foundation_credit_required"] == 7


def test_plan_requirements_summary_omits_major_foundation_credit_for_2021():
    payload = {
        "courses": [], "admission_year": 2021, "track_type": "심화과정", "track": "백엔드",
    }
    res = client.post("/api/plan", json=payload)
    assert "major_foundation_credit_required" not in res.json()["requirements_summary"]
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_api.py -k major_foundation_credit_for -v`
Expected: 첫 번째 테스트 FAIL(`KeyError`), 두 번째는 현재도 키가 없으니 이미 PASS일 수 있음 — 그래도 함께 실행해 회귀 여부를 같이 확인한다.

- [ ] **Step 3: `app/api.py` `requirements_summary` 수정**

`app/api.py:266-276`을 다음으로 교체:

```python
    # 화면이 "33/42학점"처럼 기준치를 같이 보여줘야 해서, AuditResult엔 없는 원 기준값을
    # 별도로 실어 보낸다(요청 시점의 요람 원문 요건, requirements에서 그대로 뽑음).
    industry_cert = requirements["industry_project_certification"][req.track_type]
    requirements_summary = {
        "total_credit_required": requirements["total_credit"],
        "min_gpa": requirements["min_gpa"],
        "elective_major_credit_required": requirements["elective_major_credit"][req.track_type],
        "required_major_course_count": len(requirements["required_major_courses"]),
        "industry_project_min_courses": industry_cert["min_courses"],
        "language_requirement": requirements["language_requirement"],
    }
    major_foundation_threshold = requirements.get("major_foundation_credit", {}).get(req.track_type)
    if major_foundation_threshold is not None:
        requirements_summary["major_foundation_credit_required"] = major_foundation_threshold
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_api.py -v`
Expected: 전부 PASS.

- [ ] **Step 5: `dashboard.js`에 전공기초 카드 항목 추가**

`app/static/js/dashboard.js:74-79`(`items.push({ ... name: "전공선택" ... })` 블록) 바로 뒤에 삽입:

```javascript
  if (req.major_foundation_credit_required !== undefined) {
    items.push({
      kind: a.major_foundation_certified ? "ok" : "warn",
      name: "전공기초",
      value: `${a.major_foundation_credit_earned}/${req.major_foundation_credit_required}학점`,
      detail: null,
    });
  }
```

- [ ] **Step 6: 헤드리스 브라우저로 카드 렌더링 확인**

기존 `cdp.js`/`cdp_toefl.js` 패턴을 참고해 `PLAN.requirements_summary.major_foundation_credit_required = 7`, `PLAN.audit.major_foundation_credit_earned = 4`, `major_foundation_certified: false`가 담긴 합성 `plan.json`을 세션스토리지에 주입하고 `dashboard.html`을 로드한 뒤, `#creditCard`의 `.req-name` 중 하나가 "전공기초"이고 그 옆 `.req-value`가 "4/7학점"인지 `document.querySelectorAll` 결과로 확인한다.

Expected: "전공기초" 항목이 카드에 나타나고 값이 정확함. 2021학번처럼 `major_foundation_credit_required`가 없는 시나리오에서는 이 항목 자체가 안 나타나야 함(별도로 `requirements_summary`에서 그 키를 뺀 합성 데이터로 한 번 더 확인).

- [ ] **Step 7: 커밋**

```bash
git add app/api.py app/static/js/dashboard.js tests/test_api.py
git commit -m "feat: 졸업 현황 카드에 전공기초 요건 표시(해당 학번만)"
```

---

### Task 8: 어학 자기신고 드롭다운에 신·구 시험 버전 옵션 추가

**Files:**
- Modify: `app/static/js/dashboard.js:186-193`(`buildLanguageSelfReportForm`의 `.sr-lang-exam` 옵션 목록)
- Modify: `app/static/upload.html:127-135`(`#langExam` 옵션 목록)
- Modify: `app/static/js/upload.js:302-304`(`updateLanguageFields`의 안내 문구)

**Interfaces:**
- Consumes: Task 2에서 `data/graduation_requirements.json`의 모든 학번에 들어간 `language_requirement.TEPS_NEW`(329), `TOEIC_Speaking_OLD`(5, 숫자), `IELTS`(5.5)
- Produces: 없음(화면 마지막 단) — `app/agents/session_chat.py:71-89`의 `evaluate_language_score`는 이미 문자열 threshold만 등급 서열 비교하고 숫자 threshold는 그냥 `>=` 비교하므로, 이 세 시험 모두 코드 변경 없이 바로 판정된다(Task 2 데이터만으로 이미 동작 — 이 Task는 순수 UI 노출 작업).

- [ ] **Step 1: 헤드리스 브라우저로 재현해서 현재 상태 확인**

Task 2 완료 후, 대시보드에서 `.sr-lang-exam` select의 옵션 목록에 `TEPS_NEW`/`TOEIC_Speaking_OLD`/`IELTS`가 없음을 `document.querySelector('.sr-lang-exam').innerHTML`로 확인한다(기존 `cdp_toefl.js` 패턴 재사용 — 새 스크립트를 짤 필요 없이 콘솔에서 그 한 줄만 evaluate해도 충분).

- [ ] **Step 2: `dashboard.js` 자기신고 폼에 옵션 추가**

`app/static/js/dashboard.js:186-193`을 다음으로 교체:

```javascript
    <select class="sr-lang-exam">
      <option value="">시험 선택</option>
      <option value="TOEIC">TOEIC</option>
      <option value="TEPS">TEPS (구버전)</option>
      <option value="TEPS_NEW">TEPS (뉴텝스)</option>
      <option value="TOEFL">TOEFL</option>
      <option value="GTELP">G-TELP</option>
      <option value="IELTS">IELTS</option>
      <option value="TOEIC_Speaking">TOEIC Speaking (신규, IM/IH등급)</option>
      <option value="TOEIC_Speaking_OLD">TOEIC Speaking (구버전, Level)</option>
      <option value="OPIc">OPIc</option>
    </select>
```

`TOEIC_Speaking_OLD`와 `IELTS`는 `updateSrLanguageFields`(`app/static/js/dashboard.js:217-247`)의 어떤 `if` 분기에도 안 걸리므로(TOEFL/GTELP 분기도 아니고, TOEIC_Speaking/OPIc 등급 분기도 아님) 자동으로 맨 아래 기본 숫자 입력 분기(`scoreSlot.hidden = false;`)로 떨어진다 — 코드 추가 불필요.

- [ ] **Step 3: 화면1(`upload.html`) 어학 드롭다운에도 동일하게 추가**

`app/static/upload.html:127-135`를 다음으로 교체:

```html
            <select id="langExam">
              <option value="">없음</option>
              <option value="TOEIC">TOEIC</option>
              <option value="TEPS">TEPS (구버전)</option>
              <option value="TEPS_NEW">TEPS (뉴텝스)</option>
              <option value="TOEFL">TOEFL</option>
              <option value="GTELP">G-TELP</option>
              <option value="IELTS">IELTS</option>
              <option value="TOEIC_Speaking">TOEIC Speaking (신규, IM/IH등급)</option>
              <option value="TOEIC_Speaking_OLD">TOEIC Speaking (구버전, Level)</option>
              <option value="OPIc">OPIc</option>
            </select>
```

`app/static/js/upload.js:302-304`(`updateLanguageFields`의 마지막 분기 — TOEIC/TEPS처럼 바로 점수 입력받는 시험들의 안내 문구)을 다음으로 교체:

```javascript
  // TOEIC / TEPS / TEPS_NEW / IELTS / TOEIC_Speaking_OLD — 바로 점수 입력
  setSlot("langScoreSlot", true);
  const NOTES = {
    TOEIC: "졸업 기준: 730점 이상",
    TEPS: "졸업 기준: 605점 이상(구 텝스)",
    TEPS_NEW: "졸업 기준: 329점 이상(뉴텝스)",
    IELTS: "졸업 기준: 5.5점 이상",
    TOEIC_Speaking_OLD: "졸업 기준: Level 5 이상(구버전)",
  };
  note.textContent = NOTES[exam] || "";
```

- [ ] **Step 4: 헤드리스 브라우저로 검증**

```bash
SCRATCH="/private/tmp/claude-501/-Users-minwoo-Documents-Study-AI------2------/600265f2-a15e-4a4d-bfbc-4fd9b26db127/scratchpad"
curl -s http://127.0.0.1:9333/json/version >/dev/null || \
  ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    --headless=new --remote-debugging-port=9333 --no-first-run --no-default-browser-check \
    --disable-gpu --user-data-dir="$SCRATCH/chrome-profile-verify3" \
    > "$SCRATCH/chrome_verify3.log" 2>&1 & disown)
sleep 2
```

기존 `cdp_toefl.js` 패턴을 참고해 대시보드의 `.sr-lang-exam`을 `TEPS_NEW`로 선택 → 점수 400 입력 → 제출까지 재현하고, `#creditCard`의 "어학요건" 항목이 `kind: "ok"`(충족)로 바뀌는지 확인한다(329 기준이므로 400이면 충족). 같은 방식으로 `TOEIC_Speaking_OLD`에 `3`을 입력하면 미충족(5 기준), `6`을 입력하면 충족인지도 확인한다.

Expected: 두 시나리오 모두 임계값과 정확히 일치하는 충족/미충족 판정.

- [ ] **Step 5: 커밋**

```bash
git add app/static/js/dashboard.js app/static/upload.html app/static/js/upload.js
git commit -m "feat: 어학 자기신고에 TEPS/TOEIC Speaking 신·구버전 + IELTS 옵션 추가"
```

---

## Self-Review 메모

- **스펙 커버리지**: 21~26학번 데이터(그룹 A/B/2025/2026) → Task 2. 전공기초 신설 요건 → Task 1·7. 현장실습 상한(21·22 없음/23·24 12학점/25·26 6학점) → Task 2 데이터 + 기존 `_elective_credit_earned`(코드 변경 없이 데이터만으로 동작, `app/audit.py:47-60`). 산학프로젝트 21·22 일반과정 면제 → Task 2. AI집중교육 전 학번 인정 → Task 2. 어학 시험 신·구버전 병행 인정(TEPS/TOEIC Speaking) + IELTS 신설 → Task 2(데이터, 모든 학번 공통) + Task 8(드롭다운 UI). 입학년도 자동 추론(수강년도 최솟값) → Task 3·4·5·6. 화면1 "대상 학번" 잠금 칩의 하드코딩 제거 → Task 6. 약어 매핑 명시 → Task 3.
- **플레이스홀더 스캔**: 전 Task의 코드·JSON·테스트는 실제 값으로 채워짐(TBD/TODO 없음).
- **타입 일관성**: `AuditResult.major_foundation_certified: bool | None`이 Task 1에서 정의되고 Task 7의 `dashboard.js`에서 `a.major_foundation_certified`로 그대로 소비됨. `infer_admission_year(courses: list[dict]) -> int | None`이 Task 4에서 정의되고 Task 5의 `app/api.py`에서 동일 시그니처로 호출됨. `requirements_summary.major_foundation_credit_required`가 Task 7에서 조건부로 채워지고 `dashboard.js`가 `!== undefined`로 그 존재를 확인하는 방식이 일관됨. `language_requirement`의 `TOEIC_Speaking_OLD`/`IELTS`가 숫자 타입으로 Task 2에서 정의되고, Task 8의 UI가 별도 등급 드롭다운 없이 기존 숫자 입력 경로로 자연스럽게 떨어지는 것도 `evaluate_language_score`(`app/agents/session_chat.py:71-89`)의 기존 분기(문자열=등급 서열 비교, 그 외=숫자 비교)와 일치.

## 이번 범위 밖으로 명시적으로 남긴 것

1. **로드맵(`app/agents/roadmap.py`)의 전공기초 3과목 자동 스케줄링** — 감사(audit)와 카드 표시까지만 다루고, "몇 학기에 확률및통계1을 들으세요" 같은 로드맵 추천은 하지 않는다(기존에도 전공선택 개별 과목은 스케줄링 대상이 아니라 추천 풀로만 다루는 것과 같은 수준).
2. **`data/courses.json` 카탈로그 갱신** — 확률및통계1/선형대수1/SW커리어세미나를 카탈로그에 추가하지 않는다(위 Global Constraints 사유 참고 — 어느 학번에서도 "선택형 전공선택 추천 풀"의 일부가 아니라서 카탈로그에 없는 게 맞는 상태다).
3. **챗봇(`app/agents/session_chat.py`) 자연어 슬롯필링의 어학 시험 인식** — `_parse_language_answer`가 자유 텍스트에서 시험명을 정규식으로 추출하는데, "뉴텝스"/"구 토익스피킹"/"아이엘츠" 같은 새 시험명 표현을 인식하도록 확장하진 않았다. 화면1·대시보드 카드의 구조화 드롭다운(Task 8)으로는 전부 커버되므로 챗봇 자유 질의에서만 이 시험명들을 언급했을 때 자동 매칭이 안 될 수 있다.
