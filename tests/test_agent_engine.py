"""Vertex AI Agent Engine 래퍼(agent_engine/pathfinder_agent.py) — 2026-08-24.

app/agents/supervisor.py의 LangGraph 그래프(run_full_plan)를 Vertex AI Agent
Engine에 그대로 얹기 위한 어댑터. Cloud Run(app/api.py) 배포는 그대로 두고 이건
추가 배포 대상이다(정상 동작 확인되면 갈아끼울 수 있게, 사용자 요청) — 그래서
"똑같은 판정 로직을 새로 만들지 않고 run_full_plan을 그대로 위임하는지"가 이
테스트의 핵심이다.

이 클래스 자체는 vertexai SDK를 import하지 않는다(순수 app.* + stdlib) — 그래서
메인 requirements.txt만으로도 이 테스트가 돈다. 실제 배포(agent_engine/deploy.py)만
별도 환경에서 vertexai SDK가 필요하다(protobuf 버전 충돌 회피, README.md 참고).
"""
import json

from agent_engine.pathfinder_agent import PathfinderAgentEngine


def _agent() -> PathfinderAgentEngine:
    agent = PathfinderAgentEngine()
    agent.set_up()
    return agent


def test_query_returns_json_serializable_full_plan_result():
    result = _agent().query(
        courses=[{"name": "자료구조", "credit": 3, "category": "전공필수"}],
        track="백엔드",
        taken_course_names=["자료구조"],
        taken_program_titles=[],
        remaining_terms=["3-1", "3-2"],
    )

    assert "roadmap" in result
    assert "schedule" in result["roadmap"]
    assert isinstance(result["course_recommendations"], list)
    json.dumps(result)  # 세트·데이터클래스가 안 섞여 있어야 함(직렬화 가능해야 Agent Engine이 응답 가능)


def test_query_reconstructs_manual_projects_from_plain_dicts():
    result = _agent().query(
        courses=[],
        track="백엔드",
        taken_course_names=[],
        taken_program_titles=[],
        remaining_terms=["3-1", "3-2"],
        projects=[{"title": "배달앱 클론", "field": "웹_백엔드", "is_team": True, "activity_type": "project"}],
    )

    all_evidence_names = [e["name"] for evs in result["competency_evidence"].values() for e in evs]
    assert "배달앱 클론" in all_evidence_names


def test_query_delegates_to_the_exact_same_run_full_plan_as_the_cloud_run_api():
    """app/api.py의 /api/plan과 완전히 같은 함수(run_full_plan)를 그대로 쓰는지 —
    Agent Engine 배포가 별도 판정 로직을 몰래 새로 만들지 않았다는 걸 보장한다."""
    from app.agents.supervisor import run_full_plan
    from app.parser import TranscriptData

    kwargs = dict(
        courses=[{"name": "자료구조", "credit": 3, "category": "전공필수"}],
        track="백엔드",
        taken_course_names=["자료구조"],
        taken_program_titles=[],
        remaining_terms=["3-1", "3-2"],
    )

    via_agent = _agent().query(**kwargs)
    via_direct = run_full_plan(
        TranscriptData(courses=kwargs["courses"]),
        [],
        kwargs["track"],
        taken_course_names=set(kwargs["taken_course_names"]),
        taken_program_titles=set(kwargs["taken_program_titles"]),
        remaining_terms=kwargs["remaining_terms"],
    )

    assert via_agent["roadmap"] == via_direct["roadmap"]
    assert via_agent["gap"] == via_direct["gap"]


def test_query_defaults_missing_optional_fields_gracefully():
    # projects·domain_overlay 등 선택 인자를 아예 안 넘겨도 죽지 않아야 한다
    # (Agent Engine 호출부가 최소 필드만 보낼 수도 있음).
    result = _agent().query(
        courses=[],
        track="백엔드",
        taken_course_names=[],
        taken_program_titles=[],
        remaining_terms=["3-1", "3-2"],
    )
    assert "roadmap" in result
