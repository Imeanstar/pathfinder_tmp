"""
성적표 PDF를 파싱해 과목 리스트로 구조화한다.

파이프라인 순서 (docs/plans/2026-08-20-실행계획.md Task 3-1):
  PDF 업로드(메모리 처리, 디스크 저장 금지)
    -> pdfplumber 텍스트+좌표 추출          [LLM 없음]
    -> mask_and_validate(): PII 제거+검증    [LLM 없음, 실패 시 PiiLeakDetected]
    -> 마스킹된 텍스트만 구조화 함수(Gemini)에 전송 -> 과목 리스트

핵심 로직(마스킹 순서·PII 유출 시 LLM 미호출)은 `parse_transcript_from_words`로 분리해
합성 좌표 데이터로도 검증 가능하다. `extract_words_from_pdf`(pdfplumber 경계)는
2026-08-20부터 reportlab으로 만든 실제 PDF로 통합 테스트가 있다(tests/test_parser.py,
tests/conftest.py의 build_test_transcript_pdf) — 실제 성적표 샘플이 없어도 pdfplumber
호출 자체는 검증됨. 다만 실 서비스에서 만날 진짜 아주대 포털 PDF의 레이아웃(표 구조,
폰트 임베딩 방식 등)까지 보장하진 않으니, 팀이 실 샘플을 구하면 대조 확인할 것.
"""
import io
from dataclasses import dataclass
from typing import Callable

import pdfplumber

from app.guardrail import detect_injection, increment_blocked_count, is_guardrail_enabled
from app.masking import mask_and_validate

StructureFn = Callable[[str], list[dict]]


class InjectionDetected(Exception):
    """마스킹된 텍스트에서 프롬프트 인젝션 패턴이 발견됨 — 업로드를 거부한다."""


@dataclass
class TranscriptData:
    courses: list[dict]  # [{"name": str, "credit": float, "category": str}]
    # 마스킹을 통과한 본문. 화면에서 "이렇게 가렸습니다"를 사용자에게 확인시키는 용도라
    # 응답에 실어 보낸다(2026-08-21). mask_and_validate를 통과한 텍스트라 PII가 남아있을 수
    # 없다 — 남아있으면 그 전에 PiiLeakDetected로 거부된다.
    masked_text: str = ""


def infer_admission_year(courses: list[dict]) -> int | None:
    """1학년 1학기는 휴학이 교칙상 불가능하므로, 성적표에 찍힌 "수강년도"(courses의
    "year" 키) 중 최솟값이 곧 입학년도다. 사용자가 화면에서 입학년도를 직접 입력하지
    않아도 되게 하려고 서버가 자동으로 추론한다(2026-08-22 사용자 지시). "year"가
    있는 과목이 하나도 없으면(예: 개발 모드 수동 입력) 추측하지 않고 None을 돌려준다."""
    years = [c["year"] for c in courses if "year" in c]
    return min(years) if years else None


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
    """pdfplumber 경계 코드. 원본 PDF 바이트는 이 함수 밖으로 나가지 않는다."""
    words = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            words.extend(page.extract_words())
    return words


def parse_transcript_from_words(words: list[dict], structure_fn: StructureFn) -> TranscriptData:
    """PII 마스킹 + 인젝션 검사를 통과한 텍스트만 structure_fn(LLM 호출)에 넘긴다.

    GUARDRAIL_ENABLED=false면 인젝션 검사를 건너뛴다 — 시연에서 방어 켬/끔을
    비교하기 위함(Task 3-3). PII 마스킹은 이 토글과 무관하게 항상 적용된다.
    """
    masked_text = mask_and_validate(words)
    if is_guardrail_enabled() and detect_injection(masked_text):
        increment_blocked_count()
        raise InjectionDetected("입력에서 프롬프트 인젝션 패턴이 감지되었습니다.")
    courses = structure_fn(masked_text)
    return TranscriptData(courses=courses, masked_text=masked_text)


def parse_transcript(pdf_bytes: bytes, structure_fn: StructureFn) -> TranscriptData:
    words = extract_words_from_pdf(pdf_bytes)
    return parse_transcript_from_words(words, structure_fn)
