import pytest

from app.audit import attach_citation, audit_graduation, load_requirements
from app.parser import TranscriptData


def test_audit_lists_missing_required_major_courses_by_name():
    transcript = TranscriptData(courses=[
        {"name": "자료구조", "credit": 3, "category": "전공필수"},
        {"name": "이산수학", "credit": 3, "category": "전공필수"},
        # 나머지 8개 전공필수 과목 미이수
    ])
    result = audit_graduation(transcript, admission_year=2025, track_type="심화과정",
                               requirements=load_requirements(2025))
    assert result.required_major_completed is False
    assert "알고리즘" in result.missing_required_major_courses
    assert "운영체제" in result.missing_required_major_courses
    assert "자료구조" not in result.missing_required_major_courses  # 이수했으니 빠져야 함


def test_audit_required_major_completed_when_all_ten_taken():
    ten = [
        "컴퓨터프로그래밍및실습", "이산수학", "인공지능입문", "객체지향프로그래밍및실습",
        "자료구조", "컴퓨터구조", "알고리즘", "컴퓨터네트워크", "운영체제", "시스템프로그래밍",
    ]
    transcript = TranscriptData(courses=[{"name": n, "credit": 3, "category": "전공필수"} for n in ten])
    result = audit_graduation(transcript, admission_year=2025, track_type="심화과정",
                               requirements=load_requirements(2025))
    assert result.required_major_completed is True
    assert result.missing_required_major_courses == []


def test_audit_elective_credit_sum_with_fieldwork_cap():
    # 현장실습 3과목(9학점, 원래 상한은 6학점) + 일반 전공선택 1과목(3학점)
    # 실제 인정 학점: min(9, 6) + 3 = 9 (12가 아님 — 상한 미적용이면 버그)
    transcript = TranscriptData(courses=[
        {"name": "SW현장실습1", "credit": 3, "category": "전공선택"},
        {"name": "SW현장실습2", "credit": 3, "category": "전공선택"},
        {"name": "SW현장실습3", "credit": 3, "category": "전공선택"},
        {"name": "데이터베이스", "credit": 3, "category": "전공선택"},
    ])
    result = audit_graduation(transcript, admission_year=2025, track_type="일반과정",
                               requirements=load_requirements(2025))
    assert result.elective_major_credit_earned == 9
    assert result.elective_major_certified is False  # 일반과정 기준 10학점, 9 < 10


def test_audit_excludes_major_foundation_courses_from_elective_credit():
    # 전공기초(확률및통계1 3학점, SW커리어세미나 1학점)는 전공선택과 별도 영역이라
    # 전공선택 학점 합산에 들어가면 안 된다. 전공선택 실제 이수는 6학점뿐이라
    # 일반과정 기준(10학점) 미달인데, 전공기초 4학점이 섞이면 10학점으로 잘못
    # 합산돼 충족 오판정이 났었다(2026-08-22 실사용 버그 리포트).
    transcript = TranscriptData(courses=[
        {"name": "확률및통계1", "credit": 3, "category": "전공기초"},
        {"name": "SW커리어세미나", "credit": 1, "category": "전공기초"},
        {"name": "데이터베이스", "credit": 3, "category": "전공선택"},
        {"name": "소프트웨어공학", "credit": 3, "category": "전공선택"},
    ])
    result = audit_graduation(transcript, admission_year=2025, track_type="일반과정",
                               requirements=load_requirements(2025))
    assert result.elective_major_credit_earned == 6
    assert result.elective_major_certified is False  # 일반과정 기준 10학점, 6 < 10
    assert result.total_credit_earned == 10  # 전공기초도 총 이수학점에는 포함돼야 함


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


@pytest.mark.skip(reason="Task 2에서 2021 데이터 추가 후 활성화")
def test_audit_major_foundation_certified_is_none_when_year_has_no_such_requirement():
    # 21학번은 전공기초라는 요건 자체가 없다(교필로 찍혀 전공 학점 미인정) —
    # "미충족"이 아니라 "해당 없음"이어야 한다.
    transcript = TranscriptData(courses=[])
    result = audit_graduation(transcript, admission_year=2021, track_type="심화과정",
                               requirements=load_requirements(2021))
    assert result.major_foundation_certified is None
    assert result.major_foundation_credit_earned == 0


def test_audit_industry_project_certified_with_two_courses_for_advanced_track():
    transcript = TranscriptData(courses=[
        {"name": "SW캡스톤디자인", "credit": 6, "category": "전공선택"},
        {"name": "자기주도연구1", "credit": 3, "category": "전공선택"},
    ])
    result = audit_graduation(transcript, admission_year=2025, track_type="심화과정",
                               requirements=load_requirements(2025))
    assert result.industry_project_count == 2
    assert result.industry_project_certified is True


def test_audit_industry_project_not_certified_with_one_course_for_advanced_track():
    transcript = TranscriptData(courses=[
        {"name": "SW캡스톤디자인", "credit": 6, "category": "전공선택"},
    ])
    result = audit_graduation(transcript, admission_year=2025, track_type="심화과정",
                               requirements=load_requirements(2025))
    assert result.industry_project_count == 1
    assert result.industry_project_certified is False  # 심화과정은 2과목 필요


def test_audit_flags_programming_competency_as_unresolved_for_advanced_track_only():
    transcript = TranscriptData(courses=[])
    advanced = audit_graduation(transcript, admission_year=2025, track_type="심화과정",
                                 requirements=load_requirements(2025))
    general = audit_graduation(transcript, admission_year=2025, track_type="일반과정",
                                requirements=load_requirements(2025))
    assert "programming_competency" in advanced.unresolved
    assert "programming_competency" not in general.unresolved  # 일반과정엔 해당 없는 요건


def test_audit_flags_double_major_out_of_scope_for_general_track_only():
    transcript = TranscriptData(courses=[])
    general = audit_graduation(transcript, admission_year=2025, track_type="일반과정",
                                requirements=load_requirements(2025))
    advanced = audit_graduation(transcript, admission_year=2025, track_type="심화과정",
                                 requirements=load_requirements(2025))
    assert "double_major_or_minor_out_of_scope" in general.unresolved
    assert "double_major_or_minor_out_of_scope" not in advanced.unresolved


def test_audit_language_requirement_always_unresolved_since_not_on_transcript():
    # TOEIC 등 공인 어학 성적은 성적표에 없다 — 항상 자기신고로 넘겨야 한다(Task 4-5)
    transcript = TranscriptData(courses=[])
    result = audit_graduation(transcript, admission_year=2025, track_type="심화과정",
                               requirements=load_requirements(2025))
    assert "language_requirement" in result.unresolved
    assert result.language_ok is None


def test_audit_total_credit_earned_sums_all_courses_regardless_of_category():
    transcript = TranscriptData(courses=[
        {"name": "자료구조", "credit": 3, "category": "전공필수"},
        {"name": "데이터베이스", "credit": 3, "category": "전공선택"},
        {"name": "영어", "credit": 3, "category": "대학필수"},
    ])
    result = audit_graduation(transcript, admission_year=2025, track_type="심화과정",
                               requirements=load_requirements(2025))
    assert result.total_credit_earned == 9


def test_attach_citation_uses_search_fn_top_result():
    def fake_search(query, corpus):
        assert corpus == "yoram"
        return [{"doc": f"{query}는 전공필수 과목이다", "score": 0.9, "source": "yoram"}]

    result = attach_citation(["알고리즘"], search_fn=fake_search)
    assert result == [{"item": "알고리즘", "citation": "알고리즘는 전공필수 과목이다"}]


def test_attach_citation_returns_none_when_no_hits():
    def fake_search(query, corpus):
        return []

    result = attach_citation(["요람에 없는 과목"], search_fn=fake_search)
    assert result == [{"item": "요람에 없는 과목", "citation": None}]
