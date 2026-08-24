"""Vertex AI Agent Engine 어댑터 — 서비스 고도화(2026-08-24).

app/agents/supervisor.py의 LangGraph 멀티에이전트 그래프(diagnose_competency ->
compute_gap -> course_reco/program_reco -> roadmap)를 Vertex AI Agent Engine에
그대로 얹는다. 이미 실서비스(Cloud Run, app/api.py)로 떠 있는 걸 없애는 게 아니라
**추가** 배포 대상이다 — Agent Engine에서 정상 동작이 확인되면 나중에 갈아끼울 수
있게 한다(사용자 요청). 그래서 이 파일은 새 판정 로직을 만들지 않고 기존
run_full_plan()을 그대로 위임만 한다(app/api.py의 /api/plan과 완전히 같은 함수) —
Cloud Run 버전과 Agent Engine 버전이 서로 다른 결과를 내면 "갈아끼우기" 자체가
의미 없어진다.

이 클래스는 vertexai SDK를 import하지 않는다(순수 app.* + stdlib) — Vertex AI
Agent Engine은 set_up()/query() 같은 평범한 메서드를 가진 파이썬 객체를 그대로
받아 배포한다. SDK가 필요한 건 실제 배포를 실행하는 agent_engine/deploy.py뿐이다
(별도 환경 권장 — agent_engine/README.md 참고, google-cloud-aiplatform이 요구하는
protobuf 6.x가 이 프로젝트의 google-genai 계열이 요구하는 protobuf<6.0과 충돌한다는
게 설치 시점에 실측 확인됨).
"""
from typing import Any


class PathfinderAgentEngine:
    """Vertex AI Agent Engine이 기대하는 인터페이스: set_up() 1회 호출 후 query() 반복 호출."""

    def set_up(self) -> None:
        # 지연 import — 배포 패키징 시점(agent_engine/deploy.py가 이 클래스를 pickle)엔
        # app 모듈이 아직 로드 전이어도 되고, 실제 실행 환경에서만 import되면 된다.
        from app.agents.supervisor import run_full_plan

        self._run_full_plan = run_full_plan

    def query(
        self,
        courses: list[dict],
        track: str,
        taken_course_names: list[str],
        taken_program_titles: list[str],
        remaining_terms: list[str],
        projects: list[dict] | None = None,
        domain_overlay: str | None = None,
        grad_lab_cluster: str | None = None,
        missing_required_courses: list[str] | None = None,
        missing_major_foundation_courses: list[str] | None = None,
        elective_credit_shortfall: int = 0,
        industry_project_shortfall: int = 0,
        industry_project_course_groups: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        """Agent Engine 호출 진입점. 입력은 전부 JSON 호환 타입(dict/list/str/int)만
        받는다 — run_full_plan()이 기대하는 TranscriptData·ManualProject 객체로
        여기서 변환한 뒤 그대로 위임한다.

        courses: [{"name": str, "credit": float, "category": str}, ...] — 화면1
                 업로드 결과와 같은 형태.
        projects: [{"title": str, "field": str, "is_team": bool, "activity_type": str}, ...]
        나머지 인자는 app/agents/supervisor.py의 run_full_plan()과 동일한 의미.
        """
        from app.agents.competency import ManualProject
        from app.parser import TranscriptData

        transcript = TranscriptData(courses=courses)
        manual_projects = [ManualProject(**p) for p in (projects or [])]

        result = self._run_full_plan(
            transcript,
            manual_projects,
            track,
            taken_course_names=set(taken_course_names),
            taken_program_titles=set(taken_program_titles),
            remaining_terms=remaining_terms,
            domain_overlay=domain_overlay,
            grad_lab_cluster=grad_lab_cluster,
            missing_required_courses=missing_required_courses,
            missing_major_foundation_courses=missing_major_foundation_courses,
            elective_credit_shortfall=elective_credit_shortfall,
            industry_project_shortfall=industry_project_shortfall,
            industry_project_course_groups=industry_project_course_groups,
        )

        # LangGraph state(result)엔 입력으로 넣은 transcript(TranscriptData 객체)·
        # taken_course_names/taken_program_titles(set)까지 그대로 남아있다 — 전부
        # JSON 직렬화가 안 되는 타입이라, 실제로 쓸모 있는 계산 결과 키만 골라 돌려준다
        # (app/api.py의 /api/plan 응답 중 run_full_plan이 만드는 부분과 동일한 키 집합).
        return {
            "competency_vector": result.get("competency_vector", {}),
            "competency_evidence": result.get("competency_evidence", {}),
            "competency_target": result.get("competency_target", {}),
            "competency_levels": result.get("competency_levels", {}),
            "gap": result.get("gap", {}),
            "course_recommendations": result.get("course_recommendations", []),
            "program_recommendations": result.get("program_recommendations", []),
            "roadmap": result.get("roadmap", {}),
        }
