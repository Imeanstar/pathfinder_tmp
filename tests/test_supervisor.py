import pytest

from app.agents.competency import ManualProject
from app.agents.supervisor import (
    _roadmap_node,
    run_competency_diagnosis,
    run_full_plan,
    run_recommendations,
)
from app.parser import TranscriptData


def test_run_competency_diagnosis_via_graph_matches_direct_call():
    transcript = TranscriptData(courses=[{"name": "자료구조", "credit": 3, "category": "전공필수"}])
    result = run_competency_diagnosis(transcript, projects=[], track="백엔드")
    assert result["자료구조_알고리즘"]["verified"] == 1.0


def test_run_competency_diagnosis_passes_projects_through_graph_state():
    transcript = TranscriptData(courses=[])
    project = ManualProject(title="배달앱 클론 코딩", field="웹_백엔드", is_team=True)
    result = run_competency_diagnosis(transcript, projects=[project], track="백엔드")
    assert result["협업_PM"]["self_reported"] > 0.0


def test_run_recommendations_chains_competency_gap_and_reco_nodes():
    # 아무 과목도 안 들었으니 백엔드 트랙 핵심 역량(데이터베이스 등) 격차가 커서
    # 그래프가 diagnose_competency -> compute_gap -> course/program_reco까지 다 타야 결과가 나온다
    transcript = TranscriptData(courses=[])
    result = run_recommendations(
        transcript, projects=[], track="백엔드",
        taken_course_names=set(), taken_program_titles=set(),
    )
    assert "competency_vector" in result
    assert "gap" in result
    assert result["gap"]["데이터베이스"] > 0
    assert isinstance(result["course_recommendations"], list)
    assert isinstance(result["program_recommendations"], list)
    assert len(result["course_recommendations"]) > 0
    top_course = result["course_recommendations"][0]
    assert "name" in top_course and "reason" in top_course


def test_run_recommendations_applies_domain_overlay_to_gap():
    transcript = TranscriptData(courses=[])
    result = run_recommendations(
        transcript, projects=[], track="백엔드",
        taken_course_names=set(), taken_program_titles=set(),
        domain_overlay="금융권",
    )
    assert result["gap"]["금융_핀테크지식"] > 0  # 백엔드 트랙 자체엔 없던 축이 오버레이로 들어옴


def test_run_recommendations_with_automotive_overlay_surfaces_real_hub_program():
    # 실측 검증(2026-08-20): 아주허브에 [미래자동차 Skill-UP] 시리즈가 실제로 존재하고
    # data/programs.json에 모빌리티_임베디드지식 태그로 이미 수집·태깅되어 있다.
    # 자동차 오버레이를 선택하면 그 시리즈 중 하나가 실제로 추천에 나와야 한다.
    transcript = TranscriptData(courses=[])
    result = run_recommendations(
        transcript, projects=[], track="시스템_네트워크_엔지니어",
        taken_course_names=set(), taken_program_titles=set(),
        domain_overlay="자동차",
    )
    program_names = [r["name"] for r in result["program_recommendations"]]
    assert any("미래자동차" in name for name in program_names)


def test_run_recommendations_applies_grad_lab_cluster_for_graduate_track():
    transcript = TranscriptData(courses=[])
    result = run_recommendations(
        transcript, projects=[], track="대학원_연구",
        taken_course_names=set(), taken_program_titles=set(),
        grad_lab_cluster="AI_데이터_연구실",
    )
    # AI_데이터_연구실 클러스터의 데이터_ML(0.9)이 대학원_연구 트랙 자체(0.5)보다 커서 그 값을 따라간다
    assert result["gap"]["데이터_ML"] == pytest.approx(0.9)


def test_run_full_plan_produces_a_roadmap_from_end_to_end_graph_execution():
    # 정확히 어떤 과목이 1순위로 뽑히는지는 태깅 규칙 내부 사정(다중 태그 과목이 유리)에
    # 좌우되므로 특정 과목명을 단언하지 않는다 — 여기서 검증할 것은 그래프가
    # diagnose_competency -> compute_gap -> course_reco/program_reco -> roadmap까지
    # 끊기지 않고 실행돼 학기별 스케줄(또는 배치 불가 사유)을 만들어내는가다.
    transcript = TranscriptData(courses=[{"name": "자료구조", "credit": 3, "category": "전공필수"}])
    result = run_full_plan(
        transcript, projects=[], track="백엔드",
        taken_course_names={"자료구조"}, taken_program_titles=set(),
        remaining_terms=["3-1", "3-2"],
    )
    assert "roadmap" in result
    schedule = result["roadmap"]["schedule"]
    assert set(schedule.keys()) == {"3-1", "3-2"}
    placed_count = sum(len(term["courses"]) + len(term["programs"]) for term in schedule.values())
    # 추천이 실제로 배치되거나, 안 됐다면 왜 안 됐는지 warnings에 남아야 한다 — 둘 다 비면 버그
    assert placed_count > 0 or result["roadmap"]["warnings"]


def test_run_full_plan_forwards_missing_major_foundation_courses_to_roadmap():
    # 25·26학번 신설 전공기초도 missing_required_courses와 같은 경로로 그래프를 통과해
    # roadmap 노드까지 전달돼야 자동 배치된다(2026-08-22 사용자 요청).
    transcript = TranscriptData(courses=[])
    result = run_full_plan(
        transcript, projects=[], track="백엔드",
        taken_course_names=set(), taken_program_titles=set(),
        remaining_terms=["1-1", "2-1", "2-2"],
        missing_major_foundation_courses=["SW커리어세미나", "확률및통계1", "선형대수1"],
    )
    schedule = result["roadmap"]["schedule"]
    placed_names = [c["name"] for term in schedule.values() for c in term["courses"]]
    assert "SW커리어세미나" in placed_names
    assert "확률및통계1" in placed_names
    assert "선형대수1" in placed_names


# --- 졸업요건 백필(전공선택 학점·산학프로젝트 인증) — _roadmap_node 단위 테스트 ---
# 2026-08-23 사용자 실사례: 자기신고를 많이 채워 역량 격차(gap)가 전부 0이 되면
# course_recommendations가 텅 비어, 아직 전공선택 학점·산학프로젝트 인증이 부족해도
# 로드맵에 아무 과목도 안 뜨는 문제가 있었다. _roadmap_node를 직접 호출해(그래프
# 전체를 안 돌려도) target/shortfall 조합으로 배치가 정확히 되는지 검증한다.

def test_roadmap_node_schedules_elective_backfill_using_shortfall_and_target():
    # target에서 "데이터베이스" 비중을 압도적으로 높여 백필 후보 1순위가 되게 한다
    # (course_reco.recommend_elective_backfill이 target으로 순위를 매김).
    state = {
        "course_recommendations": [],
        "program_recommendations": [],
        "taken_course_names": {"자료구조"},  # 데이터베이스의 선수과목
        "remaining_terms": ["3-1", "3-2"],
        "competency_target": {"데이터베이스": 10.0},
        "elective_credit_shortfall": 3,
    }
    result = _roadmap_node(state)
    placed = [c for term in result["roadmap"]["schedule"].values() for c in term["courses"]]
    assert any(c["name"] == "데이터베이스" for c in placed)


def test_roadmap_node_schedules_industry_project_backfill_using_shortfall_and_groups():
    state = {
        "course_recommendations": [],
        "program_recommendations": [],
        "taken_course_names": {"객체지향프로그래밍및실습"},  # 자기주도프로젝트의 선수과목
        "remaining_terms": ["3-1", "3-2"],
        "competency_target": {},
        "industry_project_shortfall": 1,
        "industry_project_course_groups": {"자기주도프로젝트과목군": ["자기주도프로젝트"]},
    }
    result = _roadmap_node(state)
    placed = [c for term in result["roadmap"]["schedule"].values() for c in term["courses"]]
    assert any(c["name"] == "자기주도프로젝트" for c in placed)


def test_roadmap_node_elective_backfill_excludes_names_already_gap_recommended():
    state = {
        "course_recommendations": [
            {"name": "데이터베이스", "reason": "격차", "credit": 3, "category": "전공선택"}
        ],
        "program_recommendations": [],
        "taken_course_names": {"자료구조"},
        "remaining_terms": ["3-1", "3-2"],
        "competency_target": {"데이터베이스": 10.0},
        "elective_credit_shortfall": 6,
    }
    result = _roadmap_node(state)
    placed = [c for term in result["roadmap"]["schedule"].values() for c in term["courses"]]
    db_entries = [c for c in placed if c["name"] == "데이터베이스"]
    assert len(db_entries) == 1  # gap 추천과 백필이 같은 과목을 중복 배치하면 안 됨


def test_roadmap_node_nets_out_gap_recommended_credit_from_elective_shortfall():
    # course_recommendations(2단계, gap 기반)가 이미 3학점을 추천했으면, shortfall
    # 3은 이미 채워진 것으로 보고 별도 백필을 추가하지 않아야 한다(과다 추천 방지).
    state = {
        "course_recommendations": [
            {"name": "데이터베이스", "reason": "격차", "credit": 3, "category": "전공선택"}
        ],
        "program_recommendations": [],
        "taken_course_names": {"자료구조"},
        "remaining_terms": ["3-1", "3-2"],
        "competency_target": {},
        "elective_credit_shortfall": 3,
    }
    result = _roadmap_node(state)
    placed = [c for term in result["roadmap"]["schedule"].values() for c in term["courses"]]
    backfill_entries = [c for c in placed if "[졸업요건] 전공선택" in c.get("reason", "")]
    assert backfill_entries == []


def test_roadmap_node_without_shortfall_state_behaves_like_before():
    # 새 state 키(elective_credit_shortfall 등)를 전혀 안 넘겨도(기존 호출부 호환)
    # 에러 없이 기존과 동일하게 동작해야 한다.
    state = {
        "course_recommendations": [],
        "program_recommendations": [],
        "taken_course_names": set(),
        "remaining_terms": [],
    }
    result = _roadmap_node(state)
    assert result["roadmap"]["schedule"] == {}


def test_run_full_plan_forwards_elective_and_industry_project_shortfall():
    # 자기주도프로젝트의 선수과목(객체지향프로그래밍및실습)을 taken에 넣어야
    # 산학프로젝트 인증 백필이 남은 학기(3-1, 3-2) 안에 실제로 배치될 수 있다.
    transcript = TranscriptData(courses=[])
    result = run_full_plan(
        transcript, projects=[], track="백엔드",
        taken_course_names={"자료구조", "객체지향프로그래밍및실습"}, taken_program_titles=set(),
        remaining_terms=["3-1", "3-2"],
        elective_credit_shortfall=3,
        industry_project_shortfall=1,
        industry_project_course_groups={"자기주도프로젝트과목군": ["자기주도프로젝트"]},
    )
    schedule = result["roadmap"]["schedule"]
    reasons = [c.get("reason", "") for term in schedule.values() for c in term["courses"]]
    assert any("[졸업요건] 전공선택" in r or "[졸업요건] 산학프로젝트 인증" in r for r in reasons)
