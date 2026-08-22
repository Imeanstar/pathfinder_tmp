"""
졸업요건 판정. 전부 순수 코드(LLM 미사용) — docs/plans Task 3-2 원칙.

공식 요람 원문(data_pipeline/yoram_official_extract.md) 기준 판정 방식:
- 전공필수: 학점 합산 아님. 10개 지정 과목 전부 이수했는지(집합 완전성)만 본다.
- 전공선택: 학점 합산. 단 현장실습 과목군은 그룹 합계를 max_credit으로 클램프한 뒤
  최종 합계에 반영한다(예: 현장실습 9학점 이수해도 인정은 6학점까지).
- 산학프로젝트 인증: 6개 과목군 전체에서 이수 과목이 몇 개인지 세는 것뿐(학점 무관).
- 성적표에 없는 항목(TOPCIT/어학성적)과 타 학과 데이터가 필요한 항목(복수전공/부전공)은
  여기서 판정하지 않고 unresolved로 넘긴다 — 전자는 Task 4-5(챗봇)가 채우고,
  후자는 화면에 "서비스 범위 밖" 고정 안내로 처리한다(범위 결정, 주제기획서.md 5-1).
"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.parser import TranscriptData

# retrieve(query, corpus) -> [{doc, score, source}] — Task 3-4가 실제 구현을 채움.
# 여기서는 의존성 주입으로 받아, RAG 없이도 attach_citation 자체를 테스트할 수 있게 한다.
SearchFn = Callable[[str, str], list[dict]]

ROOT = Path(__file__).resolve().parent.parent


def load_requirements(admission_year: int) -> dict:
    path = ROOT / "data" / "graduation_requirements.json"
    all_requirements = json.loads(path.read_text(encoding="utf-8"))
    return all_requirements[str(admission_year)]


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
    # 로드맵이 gap 추천과 무관하게 이 과목들을 우선 배치하기 위한 목록 — missing_required_major_courses와
    # 같은 역할을 전공기초에 대해 한다. 그 학번에 전공기초 요건 자체가 없으면 빈 리스트(해당 없음).
    missing_major_foundation_courses: list[str] = field(default_factory=list)


def _elective_credit_earned(elective_courses: list[dict], requirements: dict) -> int:
    cap_groups = requirements.get("elective_credit_cap_groups", {})
    capped_course_names = set()
    total = 0

    for group in cap_groups.values():
        group_courses = [c for c in elective_courses if c["name"] in group["courses"]]
        capped_course_names.update(c["name"] for c in group_courses)
        group_sum = sum(c["credit"] for c in group_courses)
        total += min(group_sum, group["max_credit"])

    uncapped_courses = [c for c in elective_courses if c["name"] not in capped_course_names]
    total += sum(c["credit"] for c in uncapped_courses)
    return total


def _industry_project_count(taken_names: set[str], requirements: dict) -> int:
    course_groups = requirements["industry_project_certification"]["course_groups"]
    all_group_courses = {name for group in course_groups.values() for name in group}
    return len(taken_names & all_group_courses)


def audit_graduation(
    transcript: TranscriptData,
    admission_year: int,
    track_type: str,
    requirements: dict,
) -> AuditResult:
    courses = transcript.courses
    taken_names = {c["name"] for c in courses}

    total_credit_earned = sum(c["credit"] for c in courses)

    required_names = {c["name"] for c in requirements["required_major_courses"]}
    missing_required = sorted(required_names - taken_names)
    required_major_completed = len(missing_required) == 0

    elective_courses = [c for c in courses if c["category"] == "전공선택"]
    elective_credit_earned = _elective_credit_earned(elective_courses, requirements)
    elective_threshold = requirements["elective_major_credit"][track_type]
    elective_major_certified = elective_credit_earned >= elective_threshold

    major_foundation_courses = [c for c in courses if c["category"] == "전공기초"]
    major_foundation_credit_earned = sum(c["credit"] for c in major_foundation_courses)
    major_foundation_threshold = requirements.get("major_foundation_credit", {}).get(track_type)
    major_foundation_certified = (
        None if major_foundation_threshold is None
        else major_foundation_credit_earned >= major_foundation_threshold
    )
    major_foundation_names = {c["name"] for c in requirements.get("major_foundation_courses", [])}
    if track_type in ("복수과정", "부전공"):
        # 요람 원문: "SW커리어세미나: 전과(전입)생 및 편입학생은 이수 의무 없음" — 이
        # 서비스는 학생 유형을 별도로 모델링하지 않으므로, 이미 전공기초 학점 기준을
        # 6(복수·부전공)/7(심화·일반)로 나눠둔 것과 같은 근거로 여기서도 제외한다.
        major_foundation_names.discard("SW커리어세미나")
    missing_major_foundation = sorted(major_foundation_names - taken_names)

    industry_project_count = _industry_project_count(taken_names, requirements)
    min_courses = requirements["industry_project_certification"][track_type]["min_courses"]
    industry_project_certified = industry_project_count >= min_courses

    unresolved = ["language_requirement"]  # 성적표에 없음 — 항상 자기신고로 넘김(Task 4-5)

    if track_type in requirements["programming_competency_certification"]["applies_to"]:
        unresolved.append("programming_competency")

    if track_type in requirements.get("requires_double_major_or_minor", []):
        unresolved.append("double_major_or_minor_out_of_scope")

    return AuditResult(
        total_credit_earned=total_credit_earned,
        required_major_completed=required_major_completed,
        missing_required_major_courses=missing_required,
        elective_major_credit_earned=elective_credit_earned,
        elective_major_certified=elective_major_certified,
        major_foundation_credit_earned=major_foundation_credit_earned,
        major_foundation_certified=major_foundation_certified,
        missing_major_foundation_courses=missing_major_foundation,
        industry_project_certified=industry_project_certified,
        industry_project_count=industry_project_count,
        language_ok=None,
        unresolved=unresolved,
    )


def attach_citation(missing_items: list[str], search_fn: SearchFn) -> list[dict]:
    """미충족 항목마다 요람 RAG 검색 결과 1위를 근거로 붙인다. 검색 결과 없으면 citation=None."""
    results = []
    for item in missing_items:
        hits = search_fn(item, "yoram")
        citation = hits[0]["doc"] if hits else None
        results.append({"item": item, "citation": citation})
    return results
