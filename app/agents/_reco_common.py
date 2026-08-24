"""
교과·비교과 추천 공통 로직(closed-set + 환각 차단) — course_reco.py/program_reco.py가 공유한다.
docs/plans Task 4-2: "DB 안의 과목/프로그램만 후보로 좁히고 LLM은 이유 설명만 생성.
LLM 출력에 후보 목록에 없는 이름이 나오면 거부하고 규칙기반 폴백."
"""
from typing import Callable, TypedDict


class Recommendation(TypedDict):
    name: str
    reason: str


SelectFn = Callable[[list[dict], dict[str, float]], list[Recommendation]]


def _gap_score(item: dict, gap: dict[str, float]) -> float:
    return sum(gap.get(tag, 0.0) for tag in item.get("competency_tags", []))


def _default_reason(item: dict, gap: dict[str, float]) -> str:
    from app.agents.competency import get_competency_label  # 순환 임포트 방지용 지연 임포트

    tags = item.get("competency_tags", [])
    if not tags:
        return "역량 격차를 채우는 데 도움이 됩니다."
    top_tag = max(tags, key=lambda t: gap.get(t, 0.0))
    return f"'{get_competency_label(top_tag)}' 역량 격차가 커서 추천합니다."


def closed_set_recommend(
    items: list[dict],
    name_field: str,
    taken_names: set[str],
    gap: dict[str, float],
    top_k: int,
    select_fn: SelectFn | None,
) -> list[Recommendation]:
    """items: 카탈로그(과목 또는 프로그램). 각 항목에 name_field와 competency_tags가 있어야 한다.

    반환값엔 name/reason 외에 원본 카탈로그 필드(과목의 credit·category, 프로그램의
    url·org·apply_period 등)를 그대로 실어 보낸다 — 화면3(로드맵)이 이 값을 그대로
    표시해야 해서다(2026-08-20 추가, 대시보드 설계 중 발견한 공백).
    """
    normalized = [
        {**item, "name": item[name_field]}
        for item in items
        if item[name_field] not in taken_names
    ]
    candidates = [c for c in normalized if _gap_score(c, gap) > 0]
    candidates.sort(key=lambda c: _gap_score(c, gap), reverse=True)

    if select_fn is not None:
        candidate_pool = candidates[:10]  # LLM에 넘기는 후보는 상위 10개로 제한
        llm_result = select_fn(candidate_pool, gap)
        candidate_by_name = {c["name"]: c for c in candidate_pool}
        if llm_result and all(r["name"] in candidate_by_name for r in llm_result):
            # LLM은 name/reason만 주므로, 원본 카탈로그 필드는 후보 풀에서 다시 병합한다.
            return [
                {**candidate_by_name[r["name"]], "reason": r["reason"]}
                for r in llm_result[:top_k]
            ]
        # 빈 결과 또는 후보에 없는 이름(환각) -> 조용히 넘기지 않고 규칙기반으로 대체

    return [
        {**c, "reason": _default_reason(c, gap)}
        for c in candidates[:top_k]
    ]
