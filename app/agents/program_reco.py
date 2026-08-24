"""비교과(아주허브 프로그램) 추천 — closed-set, docs/plans Task 4-2."""
import json
import re
from pathlib import Path

from app.agents._reco_common import Recommendation, SelectFn, closed_set_recommend

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# 대괄호 카테고리 태그("[미래자동차 Skill-UP]" 등)는 유용한 분류 정보라 남기고,
# 그 뒤 본문 맨 앞의 연도·학기·계절학기·회차 표기만 지운다(2026-08-21 사용자 요청 —
# "작년 데이터를 올해 추천에 쓰는 건데 제목에 작년 연도가 그대로 있으면 안 된다").
# "5월"처럼 숫자 뒤에 "월"이 오는 건 시기 안내로 남겨도 되는 정보라 건드리지 않는다
# (부정 전방탐색으로 보호).
_LEADING_YEAR_RE = re.compile(
    r"^(20)?\d{2}(학년도|년)?[-\s]*"
    r"(\d(?!\s*월)\s*(학기)?|상반기|하반기|하계방학|동계방학|하계|동계)?\s*"
)
_JEHOI_RE = re.compile(r"제\s*\d+\s*회\s*")
_ORDINAL_COUNT_RE = re.compile(r"\d+\s*기\s*(모집|선발|신청)")


def clean_program_title(title: str) -> str:
    m = re.match(r"^(\[[^\]]+\]\s*)(.*)$", title)
    prefix, body = (m.group(1), m.group(2)) if m else ("", title)

    body = _LEADING_YEAR_RE.sub("", body)
    body = _JEHOI_RE.sub("", body)
    body = _ORDINAL_COUNT_RE.sub(r"\1", body)

    return (prefix + body).strip()


def recommend_programs(
    gap: dict[str, float],
    taken_titles: set[str],
    top_k: int = 3,
    select_fn: SelectFn | None = None,
) -> list[Recommendation]:
    programs = json.loads((DATA_DIR / "programs.json").read_text(encoding="utf-8"))
    # 표시용 제목만 정제한다 — url/apply_period 등 나머지 카탈로그 필드와 원본
    # title은 그대로 둬서 "원문 보기" 링크 등 근거 추적에 영향이 없게 한다.
    programs = [{**p, "title": clean_program_title(p["title"])} for p in programs]
    return closed_set_recommend(programs, "title", taken_titles, gap, top_k, select_fn)
