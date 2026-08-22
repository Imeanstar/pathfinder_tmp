from dataclasses import replace

from app.agents.session_chat import (
    apply_self_reported_answers,
    build_question_list,
    evaluate_language_score,
)
from app.audit import AuditResult, load_requirements

BASE_RESULT = AuditResult(
    total_credit_earned=0,
    required_major_completed=False,
    missing_required_major_courses=[],
    elective_major_credit_earned=0,
    elective_major_certified=False,
    major_foundation_credit_earned=0,
    major_foundation_certified=None,
    industry_project_certified=False,
    industry_project_count=0,
    language_ok=None,
    unresolved=[],
)

REQUIREMENTS = load_requirements(2025)


def test_build_question_list_excludes_double_major_out_of_scope():
    questions = build_question_list(["double_major_or_minor_out_of_scope", "language_requirement"])
    reasons = [q["reason"] for q in questions]
    assert "double_major_or_minor_out_of_scope" not in reasons
    assert "language_requirement" in reasons


def test_build_question_list_only_includes_present_unresolved_reasons():
    questions = build_question_list(["language_requirement"])
    assert [q["reason"] for q in questions] == ["language_requirement"]


def test_apply_self_reported_answers_resolves_language_requirement_when_met():
    result = replace(BASE_RESULT, unresolved=["language_requirement"])
    requirements = load_requirements(2025)
    updated = apply_self_reported_answers(
        result, {"language_requirement": "토익 750점이야"}, requirements
    )
    assert updated.language_ok is True
    assert "language_requirement" not in updated.unresolved


def test_apply_self_reported_answers_resolves_language_requirement_when_not_met():
    result = replace(BASE_RESULT, unresolved=["language_requirement"])
    requirements = load_requirements(2025)
    updated = apply_self_reported_answers(
        result, {"language_requirement": "토익 600점이야"}, requirements
    )
    assert updated.language_ok is False
    assert "language_requirement" not in updated.unresolved  # 미달이어도 "알아냈다"는 사실은 해결된 것


def test_apply_self_reported_answers_keeps_unresolved_when_answer_not_understood():
    result = replace(BASE_RESULT, unresolved=["language_requirement"])
    requirements = load_requirements(2025)
    updated = apply_self_reported_answers(
        result, {"language_requirement": "잘 모르겠어"}, requirements
    )
    assert updated.language_ok is None
    assert "language_requirement" in updated.unresolved


def test_apply_self_reported_answers_certifies_programming_competency_via_topcit():
    result = replace(BASE_RESULT, unresolved=["programming_competency"])
    requirements = load_requirements(2025)
    updated = apply_self_reported_answers(
        result, {"programming_competency": "TOPCIT 200점 받았어"}, requirements
    )
    assert updated.programming_competency_certified is True
    assert "programming_competency" not in updated.unresolved


def test_apply_self_reported_answers_certifies_programming_competency_via_apc_exemption():
    result = replace(BASE_RESULT, unresolved=["programming_competency"])
    requirements = load_requirements(2025)
    updated = apply_self_reported_answers(
        result, {"programming_competency": "APC 대회에서 한 문제 정답을 맞혔어"}, requirements
    )
    assert updated.programming_competency_certified is True


def test_apply_self_reported_answers_does_not_certify_below_topcit_threshold_without_exemption():
    result = replace(BASE_RESULT, unresolved=["programming_competency"])
    requirements = load_requirements(2025)
    updated = apply_self_reported_answers(
        result, {"programming_competency": "TOPCIT 150점 받았어"}, requirements
    )
    assert updated.programming_competency_certified is False
    assert "programming_competency" not in updated.unresolved  # 미달도 "확인됨"으로 해결 처리


def test_apply_self_reported_answers_recognizes_new_teps_from_free_text():
    # 뉴텝스(329점 기준)와 구 텝스(605점 기준)는 서로 다른 시험이라 문구로 구분해야
    # 한다(2026-08-22 사용자 요청 — 학교 어학 기준표가 신·구 버전을 둘 다 인정).
    result = replace(BASE_RESULT, unresolved=["language_requirement"])
    requirements = load_requirements(2025)
    updated = apply_self_reported_answers(
        result, {"language_requirement": "뉴텝스 350점 받았어"}, requirements
    )
    assert updated.language_ok is True  # 350 >= 329(뉴텝스 기준)
    assert "language_requirement" not in updated.unresolved


def test_apply_self_reported_answers_distinguishes_new_teps_from_old_teps():
    # 같은 350점이라도 "텝스"라고만 하면 구 텝스(605점 기준)로 판정돼 미충족이어야 한다.
    result = replace(BASE_RESULT, unresolved=["language_requirement"])
    requirements = load_requirements(2025)
    updated = apply_self_reported_answers(
        result, {"language_requirement": "텝스 350점 받았어"}, requirements
    )
    assert updated.language_ok is False  # 350 < 605(구 텝스 기준)


def test_apply_self_reported_answers_recognizes_old_toeic_speaking_from_free_text():
    result = replace(BASE_RESULT, unresolved=["language_requirement"])
    requirements = load_requirements(2025)
    updated = apply_self_reported_answers(
        result, {"language_requirement": "구 토익스피킹 레벨 6이야"}, requirements
    )
    assert updated.language_ok is True  # 6 >= 5(구버전 기준)
    assert "language_requirement" not in updated.unresolved


def test_apply_self_reported_answers_recognizes_ielts_decimal_score_from_free_text():
    result = replace(BASE_RESULT, unresolved=["language_requirement"])
    requirements = load_requirements(2025)
    updated = apply_self_reported_answers(
        result, {"language_requirement": "아이엘츠 6.5 받았어"}, requirements
    )
    assert updated.language_ok is True  # 6.5 >= 5.5
    assert "language_requirement" not in updated.unresolved


def test_apply_self_reported_answers_leaves_other_unresolved_items_untouched():
    result = replace(BASE_RESULT, unresolved=["language_requirement", "double_major_or_minor_out_of_scope"])
    requirements = load_requirements(2025)
    updated = apply_self_reported_answers(
        result, {"language_requirement": "토익 750점이야"}, requirements
    )
    assert "double_major_or_minor_out_of_scope" in updated.unresolved


# --- 화면1에서 드롭다운으로 직접 고르는 어학 성적(2026-08-21 추가) ---
# 챗봇 자연어 파싱과 달리 시험 종류·점수가 이미 구조화돼 들어온다.

def test_evaluate_language_score_numeric_exam_passes_threshold():
    requirements = load_requirements(2025)
    assert evaluate_language_score("TOEIC", 750, requirements) is True
    assert evaluate_language_score("TOEIC", 700, requirements) is False


def test_evaluate_language_score_handles_toefl_subtypes():
    requirements = load_requirements(2025)
    # 요람 기준 TOEFL_iBT 72점
    assert evaluate_language_score("TOEFL_iBT", 80, requirements) is True
    assert evaluate_language_score("TOEFL_iBT", 70, requirements) is False


def test_evaluate_language_score_compares_grade_based_exams_by_rank():
    """TOEIC Speaking·OPIc은 점수가 아니라 등급이라 숫자 비교(>=)가 통하지 않는다.
    요람 기준값이 'IM1'처럼 숫자 접미사를 달고 있어 등급만 떼어내 서열로 비교해야 한다."""
    requirements = load_requirements(2025)

    # 기준 IM1 -> IM 등급 이상이면 충족
    assert evaluate_language_score("TOEIC_Speaking", "IH", requirements) is True
    assert evaluate_language_score("TOEIC_Speaking", "IM", requirements) is True
    assert evaluate_language_score("TOEIC_Speaking", "IL", requirements) is False
    assert evaluate_language_score("TOEIC_Speaking", "NM", requirements) is False

    # OPIc 기준은 IL
    assert evaluate_language_score("OPIc", "IL", requirements) is True
    assert evaluate_language_score("OPIc", "NH", requirements) is False


def test_evaluate_language_score_returns_none_for_unknown_exam():
    """모르는 시험은 '미충족'이 아니라 '판단 불가'다 — 모른다≠미충족 원칙."""
    requirements = load_requirements(2025)
    assert evaluate_language_score("듣도보도못한시험", 900, requirements) is None


# --- "없어" 같은 명시적 부정 응답 처리 (2026-08-21 실사용 버그) ---
# 예전엔 "없어"가 어느 패턴에도 안 걸려 계속 "이해 못 했다"고 같은 질문을 무한 반복했다.
# 반대로 programming_competency는 파싱 실패해도 무조건 False로 확정해버려
# "모른다≠미충족" 원칙이 깨져 있었다(가비지 입력도 "미충족"으로 감정).

def test_language_explicit_negative_resolves_to_not_met():
    result = replace(BASE_RESULT, unresolved=["language_requirement"])
    updated = apply_self_reported_answers(
        result, {"language_requirement": "없어"}, REQUIREMENTS
    )
    assert updated.language_ok is False
    assert "language_requirement" not in updated.unresolved


def test_language_negative_mixed_with_extra_text_still_resolves():
    result = replace(BASE_RESULT, unresolved=["language_requirement"])
    updated = apply_self_reported_answers(
        result, {"language_requirement": "없어. 난 뭐 듣는걸 추천해?"}, REQUIREMENTS
    )
    assert updated.language_ok is False


def test_language_pure_garbage_stays_unresolved():
    result = replace(BASE_RESULT, unresolved=["language_requirement"])
    updated = apply_self_reported_answers(
        result, {"language_requirement": "어"}, REQUIREMENTS
    )
    assert updated.language_ok is None
    assert "language_requirement" in updated.unresolved


def test_programming_competency_explicit_negative_resolves_to_not_certified():
    result = replace(BASE_RESULT, unresolved=["programming_competency"])
    updated = apply_self_reported_answers(
        result, {"programming_competency": "없어"}, REQUIREMENTS
    )
    assert updated.programming_competency_certified is False
    assert "programming_competency" not in updated.unresolved


def test_programming_competency_garbage_input_stays_unresolved():
    """가비지/IME 잔여 입력('어' 한 글자 등)이 '미충족'으로 확정되면 안 된다 —
    모른다≠미충족 원칙이 이 항목에서만 깨져 있었다(2026-08-21 실사용 중 발견)."""
    result = replace(BASE_RESULT, unresolved=["programming_competency"])
    updated = apply_self_reported_answers(
        result, {"programming_competency": "어"}, REQUIREMENTS
    )
    assert updated.programming_competency_certified is None
    assert "programming_competency" in updated.unresolved


def test_programming_competency_positive_topcit_still_works():
    result = replace(BASE_RESULT, unresolved=["programming_competency"])
    updated = apply_self_reported_answers(
        result, {"programming_competency": "TOPCIT 200점 받았어"}, REQUIREMENTS
    )
    assert updated.programming_competency_certified is True
    assert "programming_competency" not in updated.unresolved
