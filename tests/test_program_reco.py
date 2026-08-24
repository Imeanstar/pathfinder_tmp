import json
import re
from pathlib import Path

from app.agents.program_reco import clean_program_title, recommend_programs

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def test_recommend_programs_only_returns_tagged_programs_matching_gap():
    programs = json.loads((DATA_DIR / "programs.json").read_text(encoding="utf-8"))
    # 실제 데이터 기준으로 격차가 있는 역량 하나를 골라 검증(하드코딩된 프로그램명에 의존하지 않음)
    any_tag = next(t for p in programs for t in p.get("competency_tags", []))
    result = recommend_programs({any_tag: 1.0}, taken_titles=set(), top_k=3)
    for r in result:
        matched = next(p for p in programs if clean_program_title(p["title"]) == r["name"])
        assert any_tag in matched["competency_tags"]


def test_recommend_programs_excludes_already_taken_titles():
    first = recommend_programs({"협업_PM": 1.0}, taken_titles=set(), top_k=1)
    if first:  # 표본 데이터에 매칭이 없을 수도 있음 — 있을 때만 배제 검증
        excluded = recommend_programs({"협업_PM": 1.0}, taken_titles={first[0]["name"]}, top_k=1)
        assert not excluded or excluded[0]["name"] != first[0]["name"]


def test_recommend_programs_falls_back_when_llm_hallucinates():
    programs = json.loads((DATA_DIR / "programs.json").read_text(encoding="utf-8"))
    any_tag = next(t for p in programs for t in p.get("competency_tags", []))

    def hallucinating_select_fn(candidates, gap):
        return [{"name": "존재하지않는프로그램", "reason": "환각"}]

    result = recommend_programs(
        {any_tag: 1.0}, taken_titles=set(), top_k=1, select_fn=hallucinating_select_fn
    )
    titles = {p["title"] for p in programs}
    assert result[0]["name"] in titles


def test_recommend_programs_includes_catalog_metadata_for_roadmap_display():
    # 화면3(로드맵)이 원문 링크·주관부서·마감일을 보여줘야 한다(2026-08-20 추가).
    programs = json.loads((DATA_DIR / "programs.json").read_text(encoding="utf-8"))
    any_tag = next(t for p in programs for t in p.get("competency_tags", []))
    result = recommend_programs({any_tag: 1.0}, taken_titles=set(), top_k=1)
    assert "url" in result[0]
    assert "org" in result[0]
    assert "apply_period" in result[0]


# --- 프로그램 제목에서 연도·학기·회차 표기 제거 (2026-08-21 사용자 요청) ---
# "작년 데이터를 올해 추천에 쓰는 건데 제목에 작년 연도가 그대로 박혀 있으면 안 된다."

def test_clean_program_title_strips_leading_year_and_semester():
    assert clean_program_title("2025년 재맞고 사업 설명회(Q&A)") == "재맞고 사업 설명회(Q&A)"
    assert clean_program_title("2025-1 진로마블 진로탐색 프로그램") == "진로마블 진로탐색 프로그램"
    assert clean_program_title("25하반기 공기업 채용 특강") == "공기업 채용 특강"
    assert clean_program_title("2025학년도 5월 데이터보안 설명회") == "5월 데이터보안 설명회"


def test_clean_program_title_strips_round_number_but_keeps_verb():
    assert clean_program_title("PES summer camp 32기 모집(3명 선발)") == "PES summer camp 모집(3명 선발)"
    assert clean_program_title("제3회 아이디어 공모전") == "아이디어 공모전"


def test_clean_program_title_preserves_category_bracket_prefix():
    assert clean_program_title("[미래자동차 Skill-UP] 2025-2학기 ISO 26262 과정") == "[미래자동차 Skill-UP] ISO 26262 과정"


def test_clean_program_title_leaves_titles_without_year_untouched():
    assert clean_program_title("SK하이닉스 채용대비 1대1 컨설팅") == "SK하이닉스 채용대비 1대1 컨설팅"


def test_recommend_programs_returns_cleaned_titles_as_name():
    """/api/plan이 화면에 뿌리는 name은 정제된 제목이어야 한다 — 원본 title(원문 링크
    검증용)은 그대로 카탈로그에 남아있지만 표시용 name은 연도 접두사가 빠져야 한다."""
    programs = json.loads((DATA_DIR / "programs.json").read_text(encoding="utf-8"))
    any_tag = next(t for p in programs for t in p.get("competency_tags", []))
    result = recommend_programs({any_tag: 1.0}, taken_titles=set(), top_k=3)
    for r in result:
        assert r["name"] == clean_program_title(r["name"])  # 이미 정제된 상태와 같아야(멱등)
        assert not re.match(r"^(20)?\d{2}(학년도|년)?[-\s]", r["name"])
