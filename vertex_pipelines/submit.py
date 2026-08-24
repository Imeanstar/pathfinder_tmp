"""ajouhub_freshness_pipeline을 Vertex AI Pipelines에 실제로 제출한다 — 서비스
고도화(2026-08-24). 반드시 저장소 루트에서 실행한다(competency_yaml_rules_json 등을
data_pipeline/03_tag_competency.py에서 동적으로 읽어온다).

    cd ajou-pathfinder
    python3 vertex_pipelines/submit.py --project <GCP_PROJECT_ID> --bucket <STAGING_BUCKET>

기본 start/end는 .github/scripts/ajouhub_freshness.py와 같은 방식(현재
data/programs.json의 최대 id+1 ~ +201)으로 계산한다 — --start/--end로 직접
지정할 수도 있다.

별도 venv가 필요하다 — vertex_pipelines/README.md, agent_engine/README.md와 같은
이유(protobuf 충돌, google-cloud-aiplatform이 요구하는 6.x 대 google-genai
계열이 요구하는 <6.0)로 메인 .venv에 설치하면 안 된다.
"""
import argparse
import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_tag_competency_module():
    """`03_tag_competency`는 숫자로 시작해 일반 import 문으로 못 부른다 —
    파일 경로로 직접 로드한다."""
    path = REPO_ROOT / "data_pipeline" / "03_tag_competency.py"
    spec = importlib.util.spec_from_file_location("tag_competency", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _compute_default_range() -> tuple[int, int]:
    programs_path = REPO_ROOT / "data" / "programs.json"
    programs = json.loads(programs_path.read_text(encoding="utf-8"))
    max_id = max(int(p["id"].removeprefix("NCR")) for p in programs)
    return max_id + 1, max_id + 1 + 200


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="asia-northeast3")
    parser.add_argument("--bucket", required=True, help="파이프라인 루트로 쓸 GCS 버킷 이름(gs:// 접두사 없이)")
    parser.add_argument("--start", type=int, default=None, help="생략하면 현재 programs.json 최대 id+1")
    parser.add_argument("--end", type=int, default=None, help="생략하면 --start + 200")
    args = parser.parse_args()

    if Path.cwd() != REPO_ROOT:
        raise SystemExit(f"저장소 루트({REPO_ROOT})에서 실행해야 합니다.")

    compiled_path = REPO_ROOT / "vertex_pipelines" / "ajouhub_freshness_pipeline.json"
    if not compiled_path.exists():
        raise SystemExit(
            f"{compiled_path}가 없습니다 — 먼저 "
            "`python3 vertex_pipelines/ajouhub_freshness_pipeline.py`로 컴파일하세요."
        )

    default_start, default_end = _compute_default_range()
    start_id = args.start if args.start is not None else default_start
    end_id = args.end if args.end is not None else default_end

    tag_module = _load_tag_competency_module()

    from google.cloud import aiplatform

    aiplatform.init(project=args.project, location=args.location)

    job = aiplatform.PipelineJob(
        display_name="ajouhub-freshness",
        template_path=str(compiled_path),
        pipeline_root=f"gs://{args.bucket}/ajouhub-freshness",
        parameter_values={
            "start_id": start_id,
            "end_id": end_id,
            "competency_yaml_rules_json": json.dumps(tag_module.KEYWORD_RULES, ensure_ascii=False),
            "category_rules_json": json.dumps(tag_module.CATEGORY_RULES, ensure_ascii=False),
        },
    )
    job.submit()
    print(f"제출 완료 — 콘솔에서 확인: {job._dashboard_uri()}")
    print(f"수집 범위: NCR{start_id:012d} ~ NCR{end_id - 1:012d}")


if __name__ == "__main__":
    main()
