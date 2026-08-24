"""교과(전공선택) 추천 — closed-set, docs/plans Task 4-2."""
import json
from pathlib import Path

from app.agents._reco_common import Recommendation, SelectFn, _gap_score, closed_set_recommend

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def recommend_courses(
    gap: dict[str, float],
    taken_names: set[str],
    top_k: int = 3,
    select_fn: SelectFn | None = None,
) -> list[Recommendation]:
    courses = json.loads((DATA_DIR / "courses.json").read_text(encoding="utf-8"))
    return closed_set_recommend(courses, "name", taken_names, gap, top_k, select_fn)


def recommend_elective_backfill(
    taken_names: set[str],
    excluded_names: set[str],
    credit_shortfall: int,
    target: dict[str, float],
) -> list[str]:
    """역량 격차(gap) 기반 추천만으로는 전공선택 졸업 학점이 안 채워질 때 쓰는 폴백
    (2026-08-23 사용자 실사례 — 자기신고를 많이 채워 gap이 전부 0이 되면
    recommend_courses가 아무것도 안 뽑아, 아직 전공선택 학점이 부족한데도 로드맵에
    과목이 하나도 안 뜨는 문제가 있었다).

    gap 대신 target(트랙이 이 역량을 얼마나 중요하게 보는지)으로 우선순위를 매긴다 —
    gap이 이미 0이라 격차로는 더 이상 구분이 안 되지만, "진로에 더 관련 있는 과목"을
    우선하는 게 완전히 무작위로 채우는 것보다 낫다(사용자 요청).
    """
    if credit_shortfall <= 0:
        return []
    courses = json.loads((DATA_DIR / "courses.json").read_text(encoding="utf-8"))
    candidates = [
        c for c in courses
        if c["category"] == "전공선택"
        and c["name"] not in taken_names
        and c["name"] not in excluded_names
    ]
    candidates.sort(key=lambda c: _gap_score(c, target), reverse=True)

    picked: list[str] = []
    credit_sum = 0
    for c in candidates:
        if credit_sum >= credit_shortfall:
            break
        picked.append(c["name"])
        credit_sum += c["credit"]
    return picked


def recommend_industry_project_backfill(
    taken_names: set[str],
    excluded_names: set[str],
    course_groups: dict[str, list[str]],
    project_shortfall: int,
    target: dict[str, float],
) -> list[str]:
    """산학프로젝트 인증에 필요한 과목군(집중교육·자기주도프로젝트·현장실습 등) 중
    아직 안 들은 과목을, 인증까지 부족한 과목 수(project_shortfall)만큼 추천한다
    (2026-08-23, recommend_elective_backfill과 같은 이유)."""
    if project_shortfall <= 0:
        return []
    courses = json.loads((DATA_DIR / "courses.json").read_text(encoding="utf-8"))
    group_names = {name for names in course_groups.values() for name in names}
    candidates = [
        c for c in courses
        if c["name"] in group_names
        and c["name"] not in taken_names
        and c["name"] not in excluded_names
    ]
    candidates.sort(key=lambda c: _gap_score(c, target), reverse=True)
    return [c["name"] for c in candidates[:project_shortfall]]
