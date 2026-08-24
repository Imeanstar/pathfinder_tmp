import json
from pathlib import Path

from app.agents.course_reco import (
    recommend_courses,
    recommend_elective_backfill,
    recommend_industry_project_backfill,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _all_course_names() -> set[str]:
    courses = json.loads((DATA_DIR / "courses.json").read_text(encoding="utf-8"))
    return {c["name"] for c in courses}


def test_recommend_courses_prioritizes_course_matching_largest_gap():
    gap = {"데이터베이스": 1.0}
    result = recommend_courses(gap, taken_names=set(), top_k=1)
    assert len(result) == 1
    courses = json.loads((DATA_DIR / "courses.json").read_text(encoding="utf-8"))
    top = next(c for c in courses if c["name"] == result[0]["name"])
    assert "데이터베이스" in top["competency_tags"]


def test_recommend_courses_excludes_already_taken_courses():
    top_name = recommend_courses({"데이터베이스": 1.0}, taken_names=set(), top_k=1)[0]["name"]
    result = recommend_courses({"데이터베이스": 1.0}, taken_names={top_name}, top_k=1)
    assert result[0]["name"] != top_name


def test_recommend_courses_returns_nonempty_default_reason_without_llm():
    result = recommend_courses({"데이터베이스": 1.0}, taken_names=set(), top_k=1)
    assert result[0]["reason"]


def test_recommend_courses_falls_back_to_rule_based_when_llm_hallucinates():
    def hallucinating_select_fn(candidates, gap):
        return [{"name": "존재하지않는과목", "reason": "환각"}]

    result = recommend_courses(
        {"데이터베이스": 1.0}, taken_names=set(), top_k=1, select_fn=hallucinating_select_fn
    )
    assert result[0]["name"] in _all_course_names()
    assert result[0]["name"] != "존재하지않는과목"


def test_recommend_courses_trusts_valid_llm_selection():
    def valid_select_fn(candidates, gap):
        chosen = candidates[0]
        return [{"name": chosen["name"], "reason": "LLM이 설명한 이유"}]

    result = recommend_courses(
        {"데이터베이스": 1.0}, taken_names=set(), top_k=1, select_fn=valid_select_fn
    )
    assert result[0]["reason"] == "LLM이 설명한 이유"


def test_recommend_courses_ignores_competencies_with_no_gap():
    result = recommend_courses({}, taken_names=set(), top_k=3)
    assert result == []


def test_recommend_courses_includes_catalog_metadata_for_roadmap_display():
    # 화면3(로드맵)이 학점·이수구분·개설학기를 보여줘야 해서 name/reason 말고도 원본
    # 카탈로그 필드가 같이 실려야 한다(2026-08-20 추가 — 대시보드 설계 중 발견한 공백).
    result = recommend_courses({"데이터베이스": 1.0}, taken_names=set(), top_k=1)
    assert "credit" in result[0]
    assert "category" in result[0]
    assert "offered_terms" in result[0]


def test_recommend_courses_llm_selection_still_carries_catalog_metadata():
    def valid_select_fn(candidates, gap):
        chosen = candidates[0]
        return [{"name": chosen["name"], "reason": "LLM이 설명한 이유"}]

    result = recommend_courses(
        {"데이터베이스": 1.0}, taken_names=set(), top_k=1, select_fn=valid_select_fn
    )
    assert "credit" in result[0]


def test_recommend_courses_default_reason_uses_readable_label_not_raw_tag():
    """추천 사유에 '커뮤니케이션_문서화'처럼 언더바 섞인 원본 태그가 그대로 노출되면
    안 된다(2026-08-21 실사용 중 발견) — competency.yaml의 label(가운뎃점 표기)을 써야 한다."""
    result = recommend_courses({"커뮤니케이션_문서화": 1.0}, taken_names=set(), top_k=1)
    assert "커뮤니케이션_문서화" not in result[0]["reason"]
    assert "커뮤니케이션·문서화" in result[0]["reason"]


# --- 졸업요건 백필 추천 (2026-08-23) ---
# 역량 격차(gap)가 전부 0이어도(자기신고를 많이 채워 목표를 이미 넘긴 경우) 졸업에
# 필요한 전공선택 학점·산학프로젝트 인증이 남아있으면 로드맵이 계속 추천해야 한다
# (사용자 실사례 — 21학번, 140학점 중 129학점 이수, 전공선택 7학점·산학프로젝트
# 2과목이 남았는데도 역량이 충분하다는 이유로 로드맵에 아무 과목도 안 뜬 문제).

def test_recommend_elective_backfill_returns_empty_when_no_shortfall():
    assert recommend_elective_backfill(set(), set(), credit_shortfall=0, target={}) == []


def test_recommend_elective_backfill_covers_at_least_the_shortfall_credit():
    result = recommend_elective_backfill(set(), set(), credit_shortfall=6, target={})
    courses = json.loads((DATA_DIR / "courses.json").read_text(encoding="utf-8"))
    by_name = {c["name"]: c for c in courses}
    total_credit = sum(by_name[name]["credit"] for name in result)
    assert total_credit >= 6
    assert all(by_name[name]["category"] == "전공선택" for name in result)


def test_recommend_elective_backfill_excludes_taken_and_excluded_names():
    first = recommend_elective_backfill(set(), set(), credit_shortfall=3, target={})
    assert first  # 표본 데이터에 전공선택이 있으므로 최소 1개는 나와야 함
    excluded_result = recommend_elective_backfill(
        set(), set(first), credit_shortfall=3, target={}
    )
    assert not any(name in first for name in excluded_result)


def test_recommend_elective_backfill_prefers_courses_relevant_to_target():
    # 데이터베이스는 "데이터베이스" 역량 태그가 붙어있다(courses.json 기준) — target에서
    # 그 축의 비중을 압도적으로 높이면 데이터베이스가 최우선으로 뽑혀야 한다.
    result = recommend_elective_backfill(
        set(), set(), credit_shortfall=3, target={"데이터베이스": 10.0}
    )
    assert result[0] == "데이터베이스"


def test_recommend_industry_project_backfill_returns_empty_when_no_shortfall():
    course_groups = {"자기주도프로젝트과목군": ["자기주도프로젝트"]}
    assert recommend_industry_project_backfill(
        set(), set(), course_groups, project_shortfall=0, target={}
    ) == []


def test_recommend_industry_project_backfill_only_picks_from_course_groups():
    course_groups = {"자기주도프로젝트과목군": ["자기주도프로젝트"], "캡스톤디자인과목군": ["SW캡스톤디자인"]}
    result = recommend_industry_project_backfill(
        set(), set(), course_groups, project_shortfall=5, target={}
    )
    group_names = {"자기주도프로젝트", "SW캡스톤디자인"}
    assert set(result) <= group_names


def test_recommend_industry_project_backfill_respects_shortfall_count():
    course_groups = {"자기주도프로젝트과목군": ["자기주도프로젝트"], "캡스톤디자인과목군": ["SW캡스톤디자인"]}
    result = recommend_industry_project_backfill(
        set(), set(), course_groups, project_shortfall=1, target={}
    )
    assert len(result) == 1


def test_recommend_industry_project_backfill_excludes_taken_and_excluded_names():
    course_groups = {"자기주도프로젝트과목군": ["자기주도프로젝트"], "캡스톤디자인과목군": ["SW캡스톤디자인"]}
    result = recommend_industry_project_backfill(
        {"자기주도프로젝트"}, {"SW캡스톤디자인"}, course_groups, project_shortfall=5, target={}
    )
    assert result == []
