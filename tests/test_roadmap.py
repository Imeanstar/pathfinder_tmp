import json
from pathlib import Path

from app.agents.roadmap import plan_roadmap

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def test_plan_roadmap_places_course_in_earliest_offered_term_when_prereq_met():
    # 데이터베이스: offered_terms=[3-1,3-2], prereq=[자료구조] (실제 courses.json 기준)
    course_recos = [{"name": "데이터베이스", "reason": "격차 1순위"}]
    result = plan_roadmap(
        course_recommendations=course_recos,
        program_recommendations=[],
        taken_course_names={"자료구조"},
        remaining_terms=["2-2", "3-1", "3-2"],
    )
    assert any(c["name"] == "데이터베이스" for c in result["schedule"]["3-1"]["courses"])
    assert result["warnings"] == []


def test_plan_roadmap_warns_when_prereq_not_satisfiable_within_remaining_terms():
    course_recos = [{"name": "데이터베이스", "reason": "격차 1순위"}]
    result = plan_roadmap(
        course_recommendations=course_recos,
        program_recommendations=[],
        taken_course_names=set(),  # 자료구조 미이수
        remaining_terms=["3-1", "3-2"],
    )
    placed_names = [c["name"] for term in result["schedule"].values() for c in term["courses"]]
    assert "데이터베이스" not in placed_names
    assert any("데이터베이스" in w and "선수과목" in w for w in result["warnings"])


def test_plan_roadmap_warns_when_course_not_offered_in_remaining_terms():
    # 자료구조: offered_terms=[2-1,2-2] — 3학년 학기에는 개설 안 됨
    course_recos = [{"name": "자료구조", "reason": "..."}]
    result = plan_roadmap(
        course_recommendations=course_recos,
        program_recommendations=[],
        taken_course_names=set(),
        remaining_terms=["3-1", "3-2"],
    )
    assert any("자료구조" in w for w in result["warnings"])


def test_plan_roadmap_places_program_in_matching_semester_half():
    """예전엔 추천 프로그램을 전부 remaining_terms[0]에만 몰아넣어서, 그 뒤 학기는
    항상 '배치된 항목 없음'으로 텅 비었다(2026-08-21 실사용 중 발견 — 2027-1부터
    로드맵에 프로그램이 하나도 안 뜨는 버그의 원인). 신청기간 월(月)로 상반기(-1)/
    하반기(-2)를 판정해, 남은 학기 중 그 반기와 맞는 가장 이른 학기에 배치한다."""
    spring_program = {"name": "봄 프로그램", "reason": "...", "apply_period": "2025-05-01 00:00 ~ 2025-06-30 23:50"}
    fall_program = {"name": "가을 프로그램", "reason": "...", "apply_period": "2025-10-01 00:00 ~ 2025-11-30 23:50"}

    result = plan_roadmap(
        course_recommendations=[],
        program_recommendations=[spring_program, fall_program],
        taken_course_names=set(),
        remaining_terms=["2-2", "3-1", "3-2"],
    )

    assert result["schedule"]["3-1"]["programs"][0]["name"] == "봄 프로그램"
    assert result["schedule"]["2-2"]["programs"][0]["name"] == "가을 프로그램"


def test_plan_roadmap_falls_back_to_first_term_when_no_apply_period():
    program = {"name": "시기 불명 프로그램", "reason": "..."}
    result = plan_roadmap(
        course_recommendations=[],
        program_recommendations=[program],
        taken_course_names=set(),
        remaining_terms=["2-2", "3-1"],
    )
    assert result["schedule"]["2-2"]["programs"][0]["name"] == "시기 불명 프로그램"


def test_plan_roadmap_marks_programs_as_precedent_not_confirmed():
    """우리 데이터는 특정 연도 한 시점의 스냅샷이라, 미래 학기에 배치되는 프로그램은
    전부 '이 시기에 있었던 사례'일 뿐 그 해에 실제로 열린다고 보장할 수 없다
    (2026-08-21 사용자 요청 — 작년 이맘때 있었던 프로그램이면 참고용으로 추천하되
    개설 여부는 확인이 필요하다는 걸 명시해달라)."""
    program = {"name": "봄 프로그램", "reason": "...", "apply_period": "2025-05-01 00:00 ~ 2025-06-30 23:50"}
    result = plan_roadmap(
        course_recommendations=[], program_recommendations=[program],
        taken_course_names=set(), remaining_terms=["3-1"],
    )
    placed = result["schedule"]["3-1"]["programs"][0]
    assert placed["is_precedent"] is True


def test_plan_roadmap_preserves_recommendation_priority_order_within_a_term():
    # course_recommendations는 이미 격차 우선순위로 정렬되어 들어온다(Task 4-2) —
    # 같은 학기에 배치 가능하면 그 순서를 그대로 유지해야 한다
    course_recos = [
        {"name": "데이터베이스", "reason": "1순위"},
        {"name": "정보보호", "reason": "2순위"},  # offered_terms=[3-1,3-2], prereq=[자료구조]
    ]
    result = plan_roadmap(
        course_recommendations=course_recos,
        program_recommendations=[],
        taken_course_names={"자료구조"},
        remaining_terms=["3-1"],
    )
    names_in_term = [c["name"] for c in result["schedule"]["3-1"]["courses"]]
    assert names_in_term == ["데이터베이스", "정보보호"]


# --- 요람 권장 시기(recommended_terms=●, optional_terms=〈●〉) 기반 배치 (2026-08-21) ---
# 예전엔 closed_set_recommend가 뽑은 top_k 후보(gap 점수 기준)에만 의존해서, 미이수
# 전공필수 과목이 gap과 무관하다는 이유로 로드맵에서 아예 빠질 수 있었다. 전공필수는
# "성적표 없는 사람"에게도 무조건 들어야 하는 졸업요건이므로 gap 추천과 별개로 반드시
# 배치한다.

def test_plan_roadmap_places_missing_required_course_regardless_of_gap_recommendation():
    """course_recommendations(gap 기반)에 전혀 없어도, missing_required_courses로 넘긴
    전공필수는 반드시 배치 시도된다."""
    result = plan_roadmap(
        course_recommendations=[],  # gap 추천에는 하나도 없음
        program_recommendations=[],
        taken_course_names={"컴퓨터프로그래밍및실습"},
        remaining_terms=["2-1", "2-2"],
        missing_required_courses=["자료구조"],  # offered_terms=[2-1(추천),2-2(무방)]
    )
    assert any(c["name"] == "자료구조" for c in result["schedule"]["2-1"]["courses"])


def test_plan_roadmap_prefers_recommended_term_over_optional_term():
    """자료구조는 2-1이 recommended(●), 2-2가 optional(〈●〉) — 둘 다 남은 학기에
    있으면 recommended을 우선한다."""
    result = plan_roadmap(
        course_recommendations=[],
        program_recommendations=[],
        taken_course_names={"컴퓨터프로그래밍및실습"},
        remaining_terms=["2-2", "2-1"],  # 순서를 일부러 뒤섞어도 recommended가 이겨야 함
        missing_required_courses=["자료구조"],
    )
    assert any(c["name"] == "자료구조" for c in result["schedule"]["2-1"]["courses"])
    assert not any(c["name"] == "자료구조" for c in result["schedule"]["2-2"]["courses"])


def test_plan_roadmap_falls_back_to_optional_term_when_recommended_term_already_passed():
    """recommended(●) 학기가 이미 남은 학기 목록에 없으면(이미 지났으면) optional
    (〈●〉) 학기에라도 배치한다 — 아예 빠뜨리지 않는다."""
    result = plan_roadmap(
        course_recommendations=[],
        program_recommendations=[],
        taken_course_names={"컴퓨터프로그래밍및실습"},
        remaining_terms=["2-2"],  # 2-1(recommended)은 이미 지나간 학기라 remaining에 없음
        missing_required_courses=["자료구조"],
    )
    assert any(c["name"] == "자료구조" for c in result["schedule"]["2-2"]["courses"])


def test_plan_roadmap_does_not_duplicate_required_course_already_in_gap_recommendations():
    """전공필수 과목이 gap 기반 추천에도 우연히 들어있으면 중복 배치되면 안 된다."""
    result = plan_roadmap(
        course_recommendations=[{"name": "자료구조", "reason": "격차 큼"}],
        program_recommendations=[],
        taken_course_names={"컴퓨터프로그래밍및실습"},
        remaining_terms=["2-1", "2-2"],
        missing_required_courses=["자료구조"],
    )
    placed = [c["name"] for term in result["schedule"].values() for c in term["courses"]]
    assert placed.count("자료구조") == 1


# --- 전공필수 배치 순서·시기 재설계 (2026-08-21) ---
# audit.py가 missing_required_courses를 sorted()(가나다순)로 넘겨서 "알고리즘"(선수과목
# 자료구조 필요)이 "자료구조"보다 먼저 처리되던 게 실사용 중 실제로 발견된 버그의 원인이었다
# — 같은 로드맵 안에서 자료구조를 이번 학기에 배치했으면서도 "아직 안 들었다"고 판단해
# 알고리즘에 '선수과목을 먼저 들어야 한다'는 경고를 냈다. 사용자가 직접 4가지 케이스로
# 배치 규칙을 명세했다: (1) 선수과목을 이 로드맵에서 먼저 배치했으면 그 다음 학기부터 후보로
# 본다 (2) 선수과목도 안 듣고 권장 시기도 지났으면 선수과목부터 얼른, 그 다음 학기에 배치
# (3) 선수과목은 이수했는데 권장 시기가 지났으면 가장 이른 남은 학기에 바로 배치.

def test_plan_roadmap_schedules_dependent_required_course_after_prereq_placed_in_same_run():
    """missing_required_courses가 가나다순(알고리즘이 자료구조보다 먼저)으로 들어와도,
    자료구조를 이 로드맵에서 배치했으면 알고리즘은 '아직 못 듣는다'는 경고 없이 그 뒤
    학기에 배치돼야 한다. 알고리즘 recommended=[2-2], optional=[3-1] / 자료구조
    recommended=[2-1](이미 지남), optional=[2-2] (실제 courses.json 기준)."""
    result = plan_roadmap(
        course_recommendations=[],
        program_recommendations=[],
        taken_course_names={"컴퓨터프로그래밍및실습"},
        remaining_terms=["2-2", "3-1", "3-2"],
        missing_required_courses=["알고리즘", "자료구조"],  # 일부러 가나다순(선수과목 관계 역순)
    )
    courses_by_term = {
        term: [c["name"] for c in data["courses"]] for term, data in result["schedule"].items()
    }
    assert "자료구조" in courses_by_term["2-2"]
    # 같은 학기(2-2)에 자료구조와 동시에 들을 순 없으므로 알고리즘은 그 다음 후보 학기(3-1)로 밀린다
    assert "알고리즘" in courses_by_term["3-1"]
    assert "알고리즘" not in courses_by_term["2-2"]
    assert not any("알고리즘" in w and "선수과목" in w for w in result["warnings"])


def test_plan_roadmap_places_required_course_asap_when_recommended_window_already_passed():
    """자료구조(recommended=2-1, optional=2-2)를 아직 안 들었는데 남은 학기가 3-1부터
    시작하면(2-1·2-2 둘 다 이미 지남) — 조용히 빠뜨리지 않고 가장 이른 남은 학기(3-1)에
    '이미 지났으니 최대한 빨리 들으라'는 취지로 배치해야 한다."""
    result = plan_roadmap(
        course_recommendations=[],
        program_recommendations=[],
        taken_course_names={"컴퓨터프로그래밍및실습"},  # 자료구조의 선수과목은 이수함
        remaining_terms=["3-1", "3-2"],
        missing_required_courses=["자료구조"],
    )
    placed = result["schedule"]["3-1"]["courses"]
    assert any(c["name"] == "자료구조" for c in placed)
    reason = next(c["reason"] for c in placed if c["name"] == "자료구조")
    assert "지났" in reason or "최대한" in reason
    assert not any("자료구조" in w for w in result["warnings"])


def test_plan_roadmap_places_prereq_asap_then_dependent_in_next_term_when_both_overdue():
    """알고리즘·자료구조 둘 다 안 들었고 둘 다 권장 시기(2-1/2-2, 2-2/3-1)를 이미 지났으면
    (남은 학기가 3-2부터) — 자료구조부터 가장 이른 학기(3-2)에 배치하고, 알고리즘은 그
    다음 학기(4-1)에 배치해야 한다(둘 다 방치하지 않고 순서대로 따라잡기)."""
    result = plan_roadmap(
        course_recommendations=[],
        program_recommendations=[],
        taken_course_names={"컴퓨터프로그래밍및실습"},
        remaining_terms=["3-2", "4-1"],
        missing_required_courses=["알고리즘", "자료구조"],
    )
    courses_by_term = {
        term: [c["name"] for c in data["courses"]] for term, data in result["schedule"].items()
    }
    assert "자료구조" in courses_by_term["3-2"]
    assert "알고리즘" in courses_by_term["4-1"]
    assert result["warnings"] == []


# --- 전공기초(SW커리어세미나·확률및통계1·선형대수1) 자동 배치 (2026-08-22) ---
# 25·26학번부터 신설된 전공기초도 전공필수처럼 gap 추천과 무관하게 졸업하려면
# 반드시 들어야 하는 과목이다 — audit.py의 missing_major_foundation_courses를
# 그대로 로드맵에 넘겨 배치한다. 다만 카드/문구에서 "전공필수"와 혼동되지 않도록
# 사유 접두사는 "[졸업요건] 전공기초 —"로 구분한다.

def test_plan_roadmap_places_missing_major_foundation_course_regardless_of_gap_recommendation():
    # SW커리어세미나: recommended_terms=[1-1] (요람 1학년 1학기 권장, courses.json 기준)
    result = plan_roadmap(
        course_recommendations=[],
        program_recommendations=[],
        taken_course_names=set(),
        remaining_terms=["1-1", "1-2"],
        missing_major_foundation_courses=["SW커리어세미나"],
    )
    placed = result["schedule"]["1-1"]["courses"]
    assert any(c["name"] == "SW커리어세미나" for c in placed)


def test_plan_roadmap_major_foundation_reason_says_major_foundation_not_required_major():
    result = plan_roadmap(
        course_recommendations=[],
        program_recommendations=[],
        taken_course_names=set(),
        remaining_terms=["1-1"],
        missing_major_foundation_courses=["SW커리어세미나"],
    )
    reason = next(
        c["reason"] for c in result["schedule"]["1-1"]["courses"] if c["name"] == "SW커리어세미나"
    )
    assert "[졸업요건] 전공기초" in reason
    assert "전공필수" not in reason


def test_plan_roadmap_places_all_three_major_foundation_courses_in_recommended_terms():
    # 확률및통계1: recommended_terms=[2-1], 선형대수1: recommended_terms=[2-2] (courses.json 기준)
    result = plan_roadmap(
        course_recommendations=[],
        program_recommendations=[],
        taken_course_names=set(),
        remaining_terms=["1-1", "2-1", "2-2"],
        missing_major_foundation_courses=["SW커리어세미나", "확률및통계1", "선형대수1"],
    )
    courses_by_term = {
        term: [c["name"] for c in data["courses"]] for term, data in result["schedule"].items()
    }
    assert "SW커리어세미나" in courses_by_term["1-1"]
    assert "확률및통계1" in courses_by_term["2-1"]
    assert "선형대수1" in courses_by_term["2-2"]
    assert result["warnings"] == []


def test_plan_roadmap_places_overdue_major_foundation_course_asap():
    # 남은 학기가 3-1부터라 선형대수1의 권장 시기(2-2)가 이미 지났어도, 조용히
    # 빠뜨리지 않고 가장 이른 남은 학기에 배치해야 한다(전공필수와 같은 원칙).
    result = plan_roadmap(
        course_recommendations=[],
        program_recommendations=[],
        taken_course_names=set(),
        remaining_terms=["3-1", "3-2"],
        missing_major_foundation_courses=["선형대수1"],
    )
    placed = result["schedule"]["3-1"]["courses"]
    assert any(c["name"] == "선형대수1" for c in placed)
    reason = next(c["reason"] for c in placed if c["name"] == "선형대수1")
    assert "지났" in reason or "최대한" in reason
    assert result["warnings"] == []


def test_plan_roadmap_does_not_duplicate_major_foundation_course_already_taken():
    result = plan_roadmap(
        course_recommendations=[],
        program_recommendations=[],
        taken_course_names={"SW커리어세미나"},
        remaining_terms=["2-1"],
        missing_major_foundation_courses=[],  # audit.py가 이미 이수한 과목은 빼서 넘긴다
    )
    placed_names = [c["name"] for term in result["schedule"].values() for c in term["courses"]]
    assert "SW커리어세미나" not in placed_names


# --- 졸업요건 백필(전공선택 학점·산학프로젝트 인증) 배치 (2026-08-23) ---
# 역량 격차(gap)가 전부 0이라 course_recommendations가 비어도, 아직 채워야 할 전공선택
# 학점·산학프로젝트 인증 과목이 있으면 로드맵이 반드시 배치를 시도해야 한다(사용자
# 실사례 — gap이 충분해도 졸업요건이 안 채워졌으면 계속 추천해야 한다).

def test_plan_roadmap_places_missing_elective_backfill_courses_regardless_of_gap():
    # 데이터베이스: offered_terms=[3-1,3-2], prereq=[자료구조] — gap 기반 추천
    # (course_recommendations)이 텅 비어 있어도(사용자 사례처럼 gap=0)
    # missing_elective_courses로 넘긴 과목은 반드시 배치를 시도한다.
    result = plan_roadmap(
        course_recommendations=[],  # gap이 0이라 아무것도 없음
        program_recommendations=[],
        taken_course_names={"자료구조"},
        remaining_terms=["3-1", "3-2"],
        missing_elective_courses=["데이터베이스"],
    )
    placed = [c for term in result["schedule"].values() for c in term["courses"]]
    assert any(c["name"] == "데이터베이스" for c in placed)


def test_plan_roadmap_elective_backfill_reason_says_전공선택_not_전공필수():
    result = plan_roadmap(
        course_recommendations=[],
        program_recommendations=[],
        taken_course_names={"자료구조"},
        remaining_terms=["3-1", "3-2"],
        missing_elective_courses=["데이터베이스"],
    )
    placed = [c for term in result["schedule"].values() for c in term["courses"]]
    reason = next(c["reason"] for c in placed if c["name"] == "데이터베이스")
    assert "[졸업요건] 전공선택" in reason


def test_plan_roadmap_places_missing_industry_project_backfill_courses():
    # 자기주도프로젝트: offered_terms=[3-2,3-1], prereq=[객체지향프로그래밍및실습]
    result = plan_roadmap(
        course_recommendations=[],
        program_recommendations=[],
        taken_course_names={"객체지향프로그래밍및실습"},
        remaining_terms=["4-1", "4-2"],
        missing_industry_project_courses=["자기주도프로젝트"],
    )
    placed = [c for term in result["schedule"].values() for c in term["courses"]]
    assert any(c["name"] == "자기주도프로젝트" for c in placed)
    reason = next(c["reason"] for c in placed if c["name"] == "자기주도프로젝트")
    assert "[졸업요건] 산학프로젝트 인증" in reason


def test_plan_roadmap_backfill_courses_placed_overdue_when_window_passed():
    # 데이터베이스는 3학년에 권장되는데 남은 학기가 4학년뿐이면(권장 시기가 이미
    # 지났으면) 전공필수와 같은 원칙으로 조용히 빠뜨리지 않고 가장 이른 학기에
    # 밀려서라도 배치해야 한다.
    result = plan_roadmap(
        course_recommendations=[],
        program_recommendations=[],
        taken_course_names={"자료구조"},
        remaining_terms=["4-1"],
        missing_elective_courses=["데이터베이스"],
    )
    placed = result["schedule"]["4-1"]["courses"]
    assert any(c["name"] == "데이터베이스" for c in placed)
    assert result["warnings"] == []
