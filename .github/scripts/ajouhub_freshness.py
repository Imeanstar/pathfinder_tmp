"""아주허브 프로그램 신선도 유지 — 운영 자동화 계층 2.

docs/superpowers/specs/2026-08-24-운영-자동화-design.md 3.1장. ajouhub-freshness.yml이
이 스크립트로 스캔 범위를 정하고, PR 본문에 쓸 신규 프로그램 요약을 만든다. 실제
수집·태깅은 기존 data_pipeline/01_fetch_programs.py·03_tag_competency.py를 그대로 쓴다
(로직 중복 없음).

사용법:
  python3 ajouhub_freshness.py range                       # "START END" 출력
  python3 ajouhub_freshness.py summarize <이전.json> <이후.json>  # PR 본문 마크다운 출력
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WINDOW_SIZE = 200  # 0.7초 간격 기준 약 140초 — 주 1회 실행에 충분히 짧음


def _extract_id(program: dict) -> int:
    return int(program["id"].removeprefix("NCR"))


def compute_range(programs_json_path: Path) -> tuple[int, int]:
    programs = json.loads(programs_json_path.read_text(encoding="utf-8"))
    if not programs:
        raise ValueError(f"{programs_json_path}에 프로그램이 하나도 없음 — 범위를 정할 수 없음")
    max_id = max(_extract_id(p) for p in programs)
    return max_id + 1, max_id + 1 + WINDOW_SIZE


def summarize_new_programs(before_path: Path, after_path: Path) -> str:
    before_ids = {_extract_id(p) for p in json.loads(before_path.read_text(encoding="utf-8"))}
    after = json.loads(after_path.read_text(encoding="utf-8"))
    new_programs = sorted(
        (p for p in after if _extract_id(p) not in before_ids),
        key=_extract_id,
    )
    if not new_programs:
        return "새로 발견된 프로그램 없음."
    lines = [f"### 신규 프로그램 {len(new_programs)}건"]
    for p in new_programs:
        tags = ", ".join(p.get("competency_tags", [])) or "태그 없음"
        lines.append(f"- **{p['title']}** ({p['id']}) — {tags}")
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    command = sys.argv[1]
    if command == "range":
        start, end = compute_range(ROOT / "data" / "programs.json")
        print(f"{start} {end}")
        return 0

    if command == "summarize":
        if len(sys.argv) != 4:
            print("사용법: summarize <이전.json> <이후.json>", file=sys.stderr)
            return 2
        print(summarize_new_programs(Path(sys.argv[2]), Path(sys.argv[3])))
        return 0

    print(f"알 수 없는 명령: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
