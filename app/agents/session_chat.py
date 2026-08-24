"""
대화 세션 State — 성적표에 없는 요건(어학 성적, TOPCIT/APC/전국대회)을 챗봇이
물어서 채운다(docs/plans Task 4-5).

`double_major_or_minor_out_of_scope`는 질문 대상이 아니다 — 챗봇이 물어서 채울 수
있는 항목이 아니라 "이 서비스 범위 밖입니다, 학사팀에 문의하세요"로 고정 안내하는
항목이기 때문(Task 3-2 범위 결정, 주제기획서.md 5-1).

LLM 미사용: 질문지는 고정된 unresolved 사유(enum) 기반 템플릿이고, 응답 파싱도
규칙기반 정규식이다 — API 키가 없어도 전부 동작한다. 파싱에 실패하면(무슨 말인지
모르면) 그 항목은 unresolved에 그대로 남긴다 — 알아낸 척하지 않는다.
"""
import re
from dataclasses import replace

from app.audit import AuditResult

QUESTIONS = {
    "language_requirement": "졸업을 위한 공인 어학 성적이 있나요? (예: 토익 750점)",
    "programming_competency": (
        "TOPCIT 점수가 190점 이상인가요? 없다면 APC 대회에서 1문제 이상 정답을 맞혔거나, "
        "SW 관련 전국대회에서 입상한 적이 있나요?"
    ),
}

# 챗봇이 물어볼 수 없는 unresolved 사유 — "서비스 범위 밖" 고정 안내로만 처리
NOT_QUESTIONABLE = {"double_major_or_minor_out_of_scope"}


def build_question_list(unresolved: list[str]) -> list[dict]:
    """audit_graduation()의 unresolved를 실제로 물어볼 질문 목록으로 바꾼다."""
    return [
        {"reason": reason, "question": QUESTIONS[reason]}
        for reason in unresolved
        if reason not in NOT_QUESTIONABLE and reason in QUESTIONS
    ]


# "없어" 한마디에도 계속 같은 질문을 반복하던 문제(2026-08-21 실사용 중 발견) —
# 명시적 부정 표현("없다")은 "확실히 없다"는 정보이지 "이해 못 함"이 아니다.
# "모르겠다"는 반대로 진짜 모른다는 뜻이라 이 패턴에 넣으면 안 된다(별도 케이스로 남겨
# unresolved 유지 — "모른다"와 "없다"는 다른 정보다).
NEGATIVE_PATTERN = re.compile(r"없|안\s*땄|못\s*땄|아직\s*(안|못)")


# IELTS는 소수점 점수(예: 6.5)라 다른 시험처럼 int()로 바꾸면 안 된다.
_FLOAT_SCORE_EXAMS = {"IELTS"}


def _parse_language_answer(text: str) -> dict | None:
    # 뉴텝스는 "텝스"를 부분 문자열로 포함하므로, 구분되는 패턴을 일반 "텝스"보다
    # 먼저 검사해야 한다(순서가 바뀌면 "뉴텝스 350점"이 구 텝스 기준으로 잘못
    # 판정된다). 마찬가지로 "구 토익스피킹"도 순서상 먼저 온다 — 다만 신규
    # TOEIC Speaking(IM1 등 등급제)은 자유 텍스트에서 아직 인식하지 않는다(기존 갭,
    # 화면1·대시보드 드롭다운으로는 이미 선택 가능하다).
    exam_patterns = [
        ("TOEIC", r"(토익|toeic)\D{0,5}(\d{2,4})"),
        ("TEPS_NEW", r"(뉴\s*텝스|new\s*teps)\D{0,5}(\d{2,4})"),
        ("TEPS", r"(텝스|teps)\D{0,5}(\d{2,4})"),
        ("TOEFL_iBT", r"(토플\s*ibt|toefl\s*ibt)\D{0,5}(\d{2,3})"),
        ("TOEIC_Speaking_OLD", r"(구\s*토익\s*스피킹|old\s*toeic\s*speaking)\D{0,5}(\d{1,2})"),
        ("IELTS", r"(아이엘츠|ielts)\D{0,5}(\d(?:\.\d)?)"),
    ]
    for exam, pattern in exam_patterns:
        m = re.search(pattern, text, re.I)
        if m:
            raw_score = m.group(2)
            score = float(raw_score) if exam in _FLOAT_SCORE_EXAMS else int(raw_score)
            return {"exam": exam, "score": score, "negative": False}
    if NEGATIVE_PATTERN.search(text):
        return {"exam": None, "score": None, "negative": True}
    return None


# TOEIC Speaking·OPIc 등급 서열(낮은 것부터). 요람 기준값이 "IM1"처럼 숫자 접미사를
# 달고 있어(실제 TOEIC Speaking은 IM1~IM3로 세분됨) 등급 문자만 떼어 서열로 비교한다.
GRADE_ORDER = ["NL", "NM", "NH", "IL", "IM", "IH", "AL", "AM", "AH"]


def _grade_rank(value: str) -> int | None:
    normalized = re.sub(r"\d+$", "", str(value).strip().upper())
    return GRADE_ORDER.index(normalized) if normalized in GRADE_ORDER else None


def evaluate_language_score(exam: str, score, requirements: dict) -> bool | None:
    """시험 종류와 점수(또는 등급)로 어학요건 충족 여부를 판정한다.

    화면1의 어학 드롭다운(TOEIC/TEPS/TOEFL PBT·CBT·iBT/G-TELP Lv2·Lv3/TOEIC Speaking/OPIc)과
    챗봇 자연어 응답이 공유하는 판정 로직. 모르는 시험이거나 등급을 해석할 수 없으면
    None을 반환한다 — "모른다"는 "미충족"이 아니다(session_chat 전체를 관통하는 원칙).
    """
    threshold = requirements["language_requirement"].get(exam)
    if threshold is None:
        return None

    if isinstance(threshold, str):  # 등급제 시험(TOEIC Speaking, OPIc)
        got, need = _grade_rank(score), _grade_rank(threshold)
        return None if got is None or need is None else got >= need

    try:
        return float(score) >= float(threshold)
    except (TypeError, ValueError):
        return None


def _evaluate_language_requirement(answer: dict | None, requirements: dict) -> bool | None:
    if answer is None:
        return None
    if answer["negative"]:
        return False  # 명시적으로 "없다"고 답한 경우만 확정 미충족 — 애매한 침묵과 다르다
    return evaluate_language_score(answer["exam"], answer["score"], requirements)


def _parse_programming_competency_answer(text: str) -> dict | None:
    topcit_score = None
    m = re.search(r"topcit\D{0,5}(\d{2,3})", text, re.I)
    if m:
        topcit_score = int(m.group(1))
    apc_pass = bool(re.search(r"apc.{0,15}(정답|맞|통과)", text, re.I))
    contest_award = bool(re.search(r"전국대회.{0,15}(입상|수상)", text))
    negative = bool(NEGATIVE_PATTERN.search(text))
    # 숫자·키워드·부정표현 어느 것도 못 찾으면 "이해 못 함" — 가비지 입력을 미충족으로
    # 확정하지 않는다(2026-08-21 실사용 중 발견: IME 잔여 글자 "어" 한 글자가 무조건
    # "미충족"으로 감정되던 버그).
    if topcit_score is None and not apc_pass and not contest_award and not negative:
        return None
    return {
        "topcit_score": topcit_score,
        "apc_pass": apc_pass,
        "contest_award": contest_award,
        "negative": negative,
    }


def _evaluate_programming_competency(answer: dict | None, requirements: dict) -> bool | None:
    if answer is None:
        return None
    cert = requirements["programming_competency_certification"]
    if answer["apc_pass"] or answer["contest_award"]:
        return True
    if answer["topcit_score"] is not None:
        # 점수를 명확히 알아냈다면(기준 미달이어도) "확인됨" — 모른다와 다르다
        return answer["topcit_score"] >= cert["topcit_min_score"]
    if answer["negative"]:
        return False
    return None


def apply_self_reported_answers(
    audit_result: AuditResult,
    answers: dict[str, str],
    requirements: dict,
) -> AuditResult:
    """사용자의 대화 응답을 반영해 AuditResult를 갱신한다.

    "미달"로 밝혀진 것도 unresolved에서는 뺀다 — unresolved는 "모른다"는 뜻이지
    "미충족"이라는 뜻이 아니다. 파싱 실패(무슨 말인지 못 알아들음)만 unresolved로 남긴다.
    """
    language_ok = audit_result.language_ok
    programming_competency_certified = audit_result.programming_competency_certified
    unresolved = list(audit_result.unresolved)

    if "language_requirement" in answers:
        parsed = _parse_language_answer(answers["language_requirement"])
        evaluated = _evaluate_language_requirement(parsed, requirements)
        if evaluated is not None:
            language_ok = evaluated
            unresolved = [r for r in unresolved if r != "language_requirement"]

    if "programming_competency" in answers:
        parsed = _parse_programming_competency_answer(answers["programming_competency"])
        evaluated = _evaluate_programming_competency(parsed, requirements)
        if evaluated is not None:
            programming_competency_certified = evaluated
            unresolved = [r for r in unresolved if r != "programming_competency"]

    return replace(
        audit_result,
        language_ok=language_ok,
        programming_competency_certified=programming_competency_certified,
        unresolved=unresolved,
    )
