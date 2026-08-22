"""
Supervisor — LangGraph StateGraph로 에이전트 노드를 라우팅한다(주제기획서.md 3장,
실행계획 Global Constraints: 에이전트 오케스트레이션은 LangGraph로 통일).

그래프 하나를 화면마다 다른 진입점으로 재사용한다 — 화면2(현황)는 역량진단까지만,
화면3(로드맵)은 격차 계산과 교과·비교과 추천까지 전부 필요하기 때문.
Task 4-3(로드맵 배치)이 이 그래프에 마지막 노드를 추가할 예정.
"""
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.agents.competency import (
    ManualProject,
    classify_competency_levels,
    collect_competency_evidence,
    compute_gap,
    compute_target,
    diagnose_competency,
    get_domain_overlay,
    get_grad_lab_cluster,
)
from app.agents.course_reco import recommend_courses
from app.agents.program_reco import recommend_programs
from app.agents.roadmap import plan_roadmap
from app.parser import TranscriptData


class PathfinderState(TypedDict, total=False):
    transcript: TranscriptData
    projects: list[ManualProject]
    track: str
    taken_course_names: set[str]
    taken_program_titles: set[str]
    remaining_terms: list[str]
    missing_required_courses: list[str]
    missing_major_foundation_courses: list[str]
    domain_overlay: str | None
    grad_lab_cluster: str | None
    competency_vector: dict[str, dict[str, float]]
    competency_evidence: dict[str, list[dict]]
    competency_target: dict[str, float]
    competency_levels: dict[str, dict]
    gap: dict[str, float]
    course_recommendations: list[dict]
    program_recommendations: list[dict]
    roadmap: dict


def _competency_node(state: PathfinderState) -> dict:
    vector = diagnose_competency(state["transcript"], state.get("projects", []), state["track"])
    evidence = collect_competency_evidence(state["transcript"], state.get("projects", []))
    return {"competency_vector": vector, "competency_evidence": evidence}


def _resolve_overlay(state: PathfinderState) -> dict[str, float] | None:
    """도메인 오버레이(화면1 2차 드롭다운) 또는 대학원 연구실 클러스터 중 선택된 게 있으면 조회.
    대학원_연구 트랙에서만 grad_lab_cluster가 의미 있고, 그 외 트랙에선 domain_overlay를 쓴다."""
    if state.get("grad_lab_cluster"):
        return get_grad_lab_cluster(state["grad_lab_cluster"])
    if state.get("domain_overlay"):
        return get_domain_overlay(state["domain_overlay"])
    return None


def _gap_node(state: PathfinderState) -> dict:
    overlay = _resolve_overlay(state)
    gap = compute_gap(state["competency_vector"], state["track"], overlay=overlay)
    # 목표치도 같이 내보낸다 — 화면의 레이더 차트가 "목표(점선) vs 현재(실선)"를 그리려면
    # gap만으로는 부족하다(gap=0인 축의 목표를 역산할 수 없어 꽉 찬 육각형이 됐었다).
    target = compute_target(state["track"], overlay=overlay)
    # 5단계 판정(매우충족~매우부족)도 여기서 같이 낸다 — target이 있어야 "이 축이
    # 트랙과 관련 있는지"를 알 수 있어 compute_gap과 같은 노드에서 계산한다.
    # current_grade: remaining_terms 첫 학기("2-2" 등)의 앞자리 = 현재 학년. 정보가
    # 없으면(remaining_terms 없이 호출되는 화면2 경로 등) 4학년 기준(전 커리큘럼 대상)
    # 으로 보수적으로 판정한다.
    remaining_terms = state.get("remaining_terms") or []
    current_grade = int(remaining_terms[0].split("-")[0]) if remaining_terms else 4
    levels = classify_competency_levels(
        state["competency_evidence"], target, current_grade=current_grade
    )
    return {"gap": gap, "competency_target": target, "competency_levels": levels}


    # top_k 기본값(3)만 쓰면, 그 3개가 전부 선수과목 미충족일 때 로드맵에 배치할
    # 후보가 하나도 안 남아 "학기별 로드맵에 과목이 하나도 안 뜨는" 문제가 있었다
    # (2026-08-21 실사용 중 발견 — 실제로 심화 트랙 후보 3개가 전부 막혀 있었음).
    # plan_roadmap이 실제로 배치 가능한 것만 화면에 남기므로, 후보 풀을 넉넉히 늘려도
    # 화면이 산만해지지 않는다.


def _course_reco_node(state: PathfinderState) -> dict:
    result = recommend_courses(state["gap"], state.get("taken_course_names", set()), top_k=10)
    return {"course_recommendations": result}


def _program_reco_node(state: PathfinderState) -> dict:
    result = recommend_programs(state["gap"], state.get("taken_program_titles", set()), top_k=10)
    return {"program_recommendations": result}


def _roadmap_node(state: PathfinderState) -> dict:
    # remaining_terms 없이 호출되면(예: run_recommendations가 화면3 추천만 필요할 때)
    # 빈 학기 목록으로 처리 — 배치할 학기가 없다는 뜻이라 전부 warnings로 빠지지만
    # 에러는 아니다. 로드맵 자체가 필요한 호출은 run_full_plan이 remaining_terms를 채워 넘긴다.
    result = plan_roadmap(
        course_recommendations=state.get("course_recommendations", []),
        program_recommendations=state.get("program_recommendations", []),
        taken_course_names=state.get("taken_course_names", set()),
        remaining_terms=state.get("remaining_terms", []),
        missing_required_courses=state.get("missing_required_courses", []),
        missing_major_foundation_courses=state.get("missing_major_foundation_courses", []),
    )
    return {"roadmap": result}


def build_graph():
    graph = StateGraph(PathfinderState)
    graph.add_node("diagnose_competency", _competency_node)
    graph.add_node("compute_gap", _gap_node)
    graph.add_node("course_reco", _course_reco_node)
    graph.add_node("program_reco", _program_reco_node)
    graph.add_node("roadmap", _roadmap_node)

    graph.set_entry_point("diagnose_competency")
    graph.add_edge("diagnose_competency", "compute_gap")
    graph.add_edge("compute_gap", "course_reco")
    graph.add_edge("compute_gap", "program_reco")
    graph.add_edge("course_reco", "roadmap")  # course_reco/program_reco 둘 다 끝나야 roadmap 실행(fan-in)
    graph.add_edge("program_reco", "roadmap")
    graph.add_edge("roadmap", END)
    return graph.compile()


_GRAPH = build_graph()


def run_competency_diagnosis(
    transcript: TranscriptData,
    projects: list[ManualProject],
    track: str,
) -> dict[str, dict[str, float]]:
    """화면 2(현황) 진입점 — 역량진단까지만 필요하므로 diagnose_competency 노드만 직접 부른다.

    그래프 전체(_GRAPH)를 돌리지 않는 이유: compute_gap 이후 course_reco/program_reco가
    병렬로 END를 향하는 구조라, 그래프를 그대로 invoke하면 화면2엔 필요 없는 추천까지
    계산하게 된다. 노드 함수 자체는 그래프와 같은 것을 재사용해 로직 중복은 없다.
    """
    result = _competency_node({"transcript": transcript, "projects": projects, "track": track})
    return result["competency_vector"]


def run_recommendations(
    transcript: TranscriptData,
    projects: list[ManualProject],
    track: str,
    taken_course_names: set[str],
    taken_program_titles: set[str],
    domain_overlay: str | None = None,
    grad_lab_cluster: str | None = None,
) -> PathfinderState:
    """추천 목록만 필요할 때(예: 아직 남은 학기를 안 정한 상태) — 그래프 전체를 돌리되
    remaining_terms를 안 줘서 roadmap 노드는 빈 배치로 통과시킨다.

    domain_overlay: 화면1 2차 드롭다운(금융권/자동차/공공기관) 선택값, 없으면 None.
    grad_lab_cluster: track이 "대학원_연구"일 때만 의미 있는 연구실 클러스터 선택값.
    """
    return _GRAPH.invoke({
        "transcript": transcript,
        "projects": projects,
        "track": track,
        "taken_course_names": taken_course_names,
        "taken_program_titles": taken_program_titles,
        "domain_overlay": domain_overlay,
        "grad_lab_cluster": grad_lab_cluster,
    })


def run_full_plan(
    transcript: TranscriptData,
    projects: list[ManualProject],
    track: str,
    taken_course_names: set[str],
    taken_program_titles: set[str],
    remaining_terms: list[str],
    domain_overlay: str | None = None,
    grad_lab_cluster: str | None = None,
    missing_required_courses: list[str] | None = None,
    missing_major_foundation_courses: list[str] | None = None,
) -> PathfinderState:
    """화면 3(로드맵) 진입점 — 그래프 전체(역량진단→격차→추천→학기 배치)를 돈다.

    missing_required_courses: audit_graduation()이 이미 계산한 미이수 전공필수 목록.
    로드맵이 gap 추천과 무관하게 이 과목들을 우선 배치하기 위해 필요하다
    (2026-08-21, "로드맵에 과목이 하나도 안 뜬다" 문제의 근본 원인 수정).
    missing_major_foundation_courses: 같은 이유로 미이수 전공기초(25·26학번 신설) 목록도
    받는다(2026-08-22) — 그 요건이 없는 학번은 audit.py가 빈 리스트를 넘긴다.
    """
    return _GRAPH.invoke({
        "transcript": transcript,
        "projects": projects,
        "track": track,
        "taken_course_names": taken_course_names,
        "taken_program_titles": taken_program_titles,
        "remaining_terms": remaining_terms,
        "domain_overlay": domain_overlay,
        "grad_lab_cluster": grad_lab_cluster,
        "missing_required_courses": missing_required_courses or [],
        "missing_major_foundation_courses": missing_major_foundation_courses or [],
    })
