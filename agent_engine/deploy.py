"""Vertex AI Agent Engine 배포 스크립트 — 서비스 고도화(2026-08-24).

app/agents/supervisor.py의 LangGraph 멀티에이전트 그래프를 감싼
agent_engine/pathfinder_agent.py:PathfinderAgentEngine을 Vertex AI Agent
Engine에 배포한다. 기존 Cloud Run 배포(app/api.py, `.github/workflows/deploy.yml`)는
그대로 두는 **추가** 배포다.

반드시 저장소 루트에서 실행해야 한다(extra_packages의 상대경로가 app/agents/
course_reco.py 등이 계산하는 DATA_DIR 상대경로와 맞물린다):

    cd ajou-pathfinder  # 저장소 루트
    python3 agent_engine/deploy.py --project <GCP_PROJECT_ID> --bucket <STAGING_BUCKET>

이 스크립트가 요구하는 google-cloud-aiplatform[agent_engines,langgraph]는 이
프로젝트 메인 venv(.venv, requirements.txt)에 설치하면 안 된다 — 요구하는
protobuf(6.x)가 google-genai 계열이 요구하는 protobuf(<6.0)와 충돌한다(설치
시점에 실측 확인됨, requirements.txt·requirements-runtime.txt의 기존 protobuf
충돌 주석과 같은 종류의 문제). 별도 venv를 새로 만들어 이 파일 하나만 그 안에서
실행한다:

    python3 -m venv .venv-agent-engine
    source .venv-agent-engine/bin/activate
    pip install "google-cloud-aiplatform[agent_engines,langgraph]"
    python3 agent_engine/deploy.py --project <GCP_PROJECT_ID> --bucket <STAGING_BUCKET>

agent_engine/pathfinder_agent.py 자체(배포되는 코드)는 이 SDK를 전혀 import하지
않으므로, 원격 런타임엔 agent_engine/requirements.txt(가볍고 충돌 없음)만 설치된다
— 이 스크립트를 실행하는 로컬 환경에만 SDK가 필요하다.
"""
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="GCP 프로젝트 ID")
    parser.add_argument("--location", default="asia-northeast3", help="배포 리전(기본: asia-northeast3)")
    parser.add_argument("--bucket", required=True, help="스테이징용 GCS 버킷 이름(gs:// 접두사 없이)")
    parser.add_argument(
        "--update-resource-name",
        default=None,
        help="이미 배포된 Agent Engine 리소스를 갱신하려면 그 resource name을 넘긴다"
        "(예: projects/123/locations/asia-northeast3/reasoningEngines/456)."
        " 안 넘기면 새로 만든다.",
    )
    args = parser.parse_args()

    if Path.cwd() != REPO_ROOT:
        raise SystemExit(
            f"저장소 루트({REPO_ROOT})에서 실행해야 합니다 — extra_packages의 상대경로가 "
            "app/agents/*.py가 계산하는 데이터 파일 경로와 맞물려 있습니다."
        )

    import vertexai
    from vertexai import agent_engines

    from agent_engine.pathfinder_agent import PathfinderAgentEngine

    vertexai.init(project=args.project, location=args.location, staging_bucket=f"gs://{args.bucket}")

    requirements = (REPO_ROOT / "agent_engine" / "requirements.txt").read_text(encoding="utf-8")
    requirements_list = [
        line.strip() for line in requirements.splitlines() if line.strip() and not line.startswith("#")
    ]

    # app/agents/course_reco.py 등이 DATA_DIR = .../app/agents/../../data 로 상대경로를
    # 계산하므로, 원격에서도 같은 상대 위치에 놓이도록 app/ 옆에 data 파일들을 그대로 둔다.
    extra_packages = [
        "app",
        "data/courses.json",
        "data/programs.json",
        "data_pipeline/competency.yaml",
    ]

    kwargs = dict(
        agent_engine=PathfinderAgentEngine(),
        requirements=requirements_list,
        extra_packages=extra_packages,
        display_name="AJOU Pathfinder — 졸업요건 판정 멀티에이전트",
        description=(
            "app/agents/supervisor.py의 LangGraph 그래프(diagnose_competency -> "
            "compute_gap -> course_reco/program_reco -> roadmap)를 그대로 배포한 것. "
            "Cloud Run(app/api.py)과 동일한 run_full_plan()을 호출한다."
        ),
    )

    if args.update_resource_name:
        remote_agent = agent_engines.update(resource_name=args.update_resource_name, **kwargs)
        print(f"업데이트 완료: {remote_agent.resource_name}")
    else:
        remote_agent = agent_engines.create(**kwargs)
        print(f"배포 완료: {remote_agent.resource_name}")

    print("\n다음 코드로 호출해 확인하세요:")
    print(f'  remote_agent = agent_engines.get("{remote_agent.resource_name}")')
    print(
        "  remote_agent.query(courses=[{'name':'자료구조','credit':3,'category':'전공필수'}], "
        "track='백엔드', taken_course_names=['자료구조'], taken_program_titles=[], "
        "remaining_terms=['3-1','3-2'])"
    )


if __name__ == "__main__":
    main()
