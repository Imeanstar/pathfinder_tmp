"""
로드맵 배치 — 선수과목·개설학기 제약을 반영해 추천 항목을 학기별로 배치한다.
결정론적 코드, LLM 미사용(docs/plans Task 4-3).

과목: 요람은 과목마다 "이 학기에 듣는 걸 강력 추천"(recommended_terms, 원문 ●)과
"이때 들어도 무방"(optional_terms, 원문 〈●〉)을 구분해서 표시한다 — 예전엔 이 둘을
구분 없이 합쳐 "언제 개설되든 상관없다"는 듯 배치해서 "무슨 근거로 이 학기에
추천하냐"는 지적을 받았다(2026-08-21, 사용자가 요람 표를 캡처해 직접 지적).
이제 각 remaining_term에서 recommended_terms를 먼저 시도하고, 없으면
optional_terms로 대체한다(권장 시기가 이미 지난 경우에도 빠뜨리지 않기 위함) —
선수과목을 이미 이수했는지(prereq, taken 과목과 이 로드맵에서 그보다 앞서 배치된
과목 포함)도 함께 만족해야 한다. 만족하는 학기가 없으면 배치하지 않고 이유를
경고로 남긴다 — 조용히 빠뜨리지 않는다.

전공필수: 아직 안 들은 전공필수 과목은 역량 격차(gap) 추천에 뽑히지 않았어도
무조건 배치를 시도한다 — 졸업하려면 결국 다 들어야 하는 과목이라 "이 사람 진로엔
필요 없어 보인다"는 이유로 로드맵에서 빠지면 안 된다(2026-08-20 실사용 중 발견:
gap 기반 top_k 후보에 안 걸려 로드맵에 과목이 하나도 안 뜨던 문제의 근본 원인).

전공필수 배치 순서·시기 판정(2026-08-21 재설계, 사용자가 직접 4가지 케이스로 명세):
missing_required_courses는 audit.py에서 sorted()(가나다순)로 넘어오므로 "알고리즘"이
"자료구조"보다 먼저 오는 등 선수과목 관계와 무관한 순서다 — 이 순서 그대로 배치하면
"자료구조를 이번 로드맵에 넣었으면서도 아직 안 들었다고 판단해 알고리즘을 못 넣는" 버그가
생긴다(실사용 중 발견). _topological_order_required_courses()로 선수과목이 먼저 오도록
재정렬하고, 각 과목을 배치할 때 그 선수과목이 이 로드맵의 더 앞선 학기에 배치돼 있으면
(실제로 이수한 게 아니어도) "그때쯤엔 들었을 것"으로 가정해 그 학기 다음부터 후보 학기로
삼는다(assigned_terms로 추적). 이렇게 좁힌 후보 학기 안에서 recommended → optional 순으로
찾되, 그래도 없으면(권장 시기 자체가 이미 지남) 전공필수는 조용히 빠뜨리지 않고 후보 중
가장 이른 학기에 밀려서라도 배치한다(overdue) — 선수과목이 이제 막 이 로드맵에서 배치된
경우 그 다음 학기가, 이미 이수한 경우 남은 첫 학기가 자연히 "가장 이른 학기"가 된다.

프로그램: 예전엔 추천 프로그램을 전부 remaining_terms[0](가장 이른 학기)에만 몰아넣어서
그 뒤 학기는 항상 텅 비었다(2026-08-21 실사용 중 발견). 신청기간의 시작월로 상반기
(3~8월, "-1" 학기)/하반기(9~2월, "-2" 학기)를 판정해 남은 학기 중 그 반기와 맞는
가장 이른 학기에 배치한다. 우리 데이터는 특정 연도 한 시점의 스냅샷이라(전체 아주허브
수집 전, 알려진 한계) 미래 학기에 배치되는 프로그램은 "그 해 그 시기에 실제로 열린다"는
보장이 아니라 "이맘때 이런 프로그램이 있었다"는 참고 사례다 — `is_precedent` 플래그로
표시해 화면이 "개설 여부 확인 필요"를 안내할 수 있게 한다.
"""
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _semester_half(apply_period: str | None) -> str | None:
    """신청기간 문자열에서 시작월을 뽑아 상반기('1')/하반기('2')를 판정한다."""
    if not apply_period:
        return None
    m = re.search(r"\d{4}-(\d{2})-\d{2}", apply_period)
    if not m:
        return None
    month = int(m.group(1))
    return "1" if 3 <= month <= 8 else "2"


def _target_term_for_program(reco: dict, remaining_terms: list[str], schedule: dict) -> str:
    half = _semester_half(reco.get("apply_period"))
    candidates = [t for t in remaining_terms if t.endswith(f"-{half}")] if half else []
    if not candidates:
        candidates = remaining_terms
    # 같은 반기에 맞는 학기가 여러 개면(예: 봄 프로그램 여러 건) 이미 채워진 학기부터
    # 몰리지 않도록, 지금까지 프로그램이 가장 적게 배치된 학기를 우선한다(단순 라운드로빈).
    return min(candidates, key=lambda t: len(schedule[t]["programs"]))


def _load_course_catalog() -> dict[str, dict]:
    courses = json.loads((DATA_DIR / "courses.json").read_text(encoding="utf-8"))
    return {c["name"]: c for c in courses}


def _earliest_matching_term(info: dict, candidate_terms: list[str]) -> tuple[str | None, bool]:
    """recommended_terms(●)를 먼저 찾고, 없으면 optional_terms(〈●〉)를 찾는다.
    반환: (배치할 학기 또는 None, 그 학기가 recommended였는지 여부)"""
    recommended = info.get("recommended_terms", info.get("offered_terms", []))
    optional = info.get("optional_terms", [])
    for term in candidate_terms:
        if term in recommended:
            return term, True
    for term in candidate_terms:
        if term in optional:
            return term, False
    return None, False


def _topological_order_required_courses(names: list[str], catalog: dict) -> list[str]:
    """missing_required_courses는 audit.py에서 가나다순으로 넘어와 선수과목 관계와
    무관하다 — 선수과목(이 목록 안에 있는 것만)이 먼저 오도록 재정렬해야 같은 배치
    실행 안에서 "자료구조를 방금 넣었으면서도 아직 안 들었다"고 오판하지 않는다."""
    names_set = set(names)
    ordered: list[str] = []
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited or name not in names_set:
            return
        visited.add(name)
        info = catalog.get(name)
        for prereq in (info.get("prereq", []) if info else []):
            visit(prereq)
        ordered.append(name)

    for name in names:
        visit(name)
    return ordered


def _place_one_course(
    name: str, reason: str, catalog: dict, schedule: dict, taken: set,
    assigned_terms: dict[str, str], remaining_terms: list[str], warnings: list[str],
    required_label: str | None,
) -> None:
    info = catalog.get(name)
    if info is None:
        warnings.append(f"'{name}'을(를) 교육과정 카탈로그에서 찾을 수 없습니다.")
        return

    prereqs = info.get("prereq", [])
    # 실제로 이수했거나(taken), 이 로드맵 안에서 이미 배치돼 있으면(assigned_terms) "그때쯤엔
    # 들었을 것"으로 간주한다 — 둘 다 아닌 선수과목만 진짜로 배치 불가 사유가 된다.
    unmet_prereqs = [p for p in prereqs if p not in taken and p not in assigned_terms]
    if unmet_prereqs:
        warnings.append(
            f"'{name}'은(는) 선수과목({', '.join(unmet_prereqs)})을 먼저 들어야 배치할 수 있습니다."
        )
        return

    # 선수과목이 이 로드맵에서 배치된 경우, 같은 학기나 그 이전 학기엔 동시에/먼저 들을 수
    # 없으므로 그 다음 학기부터 후보로 삼는다. 이미 이수한 선수과목은 remaining_terms 시작
    # 이전이라 후보 범위에 영향 없다(기존 동작 그대로).
    earliest_index = 0
    for prereq in prereqs:
        if prereq in assigned_terms:
            earliest_index = max(earliest_index, remaining_terms.index(assigned_terms[prereq]) + 1)
    candidate_terms = remaining_terms[earliest_index:]

    if not candidate_terms:
        warnings.append(f"'{name}'은(는) 선수과목 이수 이후 남은 학기가 없어 배치할 수 없습니다.")
        return

    term, is_recommended = _earliest_matching_term(info, candidate_terms)
    overdue = False
    if term is None:
        if required_label is not None:
            # 요람 권장/허용 시기를 이미 지났어도 졸업을 위해선 결국 들어야 하므로, 조용히
            # 빠뜨리지 않고 후보 중 가장 이른 학기에 밀려서라도 배치한다(2026-08-21 사용자
            # 요청 — "얼른 이수하도록" 안내).
            term = candidate_terms[0]
            overdue = True
        else:
            warnings.append(f"'{name}'은(는) 남은 학기({', '.join(remaining_terms)}) 안에 개설되지 않습니다.")
            return

    grade, sem = term.split("-")
    if overdue:
        timing_note = f"요람 권장 시기가 이미 지났습니다 — {grade}학년 {sem}학기에 최대한 빨리 이수하세요."
    elif is_recommended:
        timing_note = f"요람 권장 학기({grade}학년 {sem}학기)입니다."
    else:
        timing_note = f"요람상 이 시기({grade}학년 {sem}학기)에 들어도 무방합니다."

    prefix = f"[졸업요건] {required_label} — " if required_label is not None else ""
    schedule[term]["courses"].append({
        "name": name, "credit": info.get("credit"), "category": info.get("category"),
        "reason": f"{prefix}{reason} {timing_note}",
    })
    assigned_terms[name] = term


def plan_roadmap(
    course_recommendations: list[dict],
    program_recommendations: list[dict],
    taken_course_names: set[str],
    remaining_terms: list[str],
    missing_required_courses: list[str] | None = None,
    missing_major_foundation_courses: list[str] | None = None,
    missing_elective_courses: list[str] | None = None,
    missing_industry_project_courses: list[str] | None = None,
) -> dict:
    catalog = _load_course_catalog()
    schedule = {term: {"courses": [], "programs": []} for term in remaining_terms}
    warnings: list[str] = []

    taken = set(taken_course_names)  # 실제 이수(성적표) — 배치 중엔 바뀌지 않는다
    assigned_terms: dict[str, str] = {}  # 이 로드맵에서 배치한 과목 -> 배치된 학기

    # 1단계: 미이수 전공필수 — gap 추천과 무관하게 무조건 배치 시도(졸업요건이므로).
    # 선수과목이 이 목록 안에도 있으면 그 과목부터 먼저 처리해야 하므로 위상 정렬한다.
    ordered_required = _topological_order_required_courses(missing_required_courses or [], catalog)
    for name in ordered_required:
        _place_one_course(
            name, "졸업을 위해 반드시 이수해야 합니다.", catalog, schedule, taken,
            assigned_terms, remaining_terms, warnings, required_label="전공필수",
        )

    # 1.5단계: 미이수 전공기초(25·26학번 신설) — 전공필수와 같은 원칙으로 gap 추천과
    # 무관하게 무조건 배치 시도한다. 그 요건 자체가 없는 학번은 audit.py가 빈 리스트를
    # 넘기므로 이 단계가 자연히 아무 일도 하지 않는다.
    ordered_major_foundation = _topological_order_required_courses(
        missing_major_foundation_courses or [], catalog
    )
    for name in ordered_major_foundation:
        _place_one_course(
            name, "졸업을 위해 반드시 이수해야 합니다.", catalog, schedule, taken,
            assigned_terms, remaining_terms, warnings, required_label="전공기초",
        )

    # 1.75단계: 전공선택 학점 백필 — 역량 격차(gap) 기반 추천(2단계)만으로는 졸업에
    # 필요한 전공선택 학점이 안 채워질 때(특히 gap이 전부 0이면 2단계가 아예 텅 빈다)
    # course_reco.recommend_elective_backfill이 미리 골라준 과목을 무조건 배치한다
    # (2026-08-23 사용자 실사례 — 역량은 충분한데 전공선택 학점이 부족한데도 로드맵에
    # 과목이 하나도 안 뜬 문제).
    ordered_elective_backfill = _topological_order_required_courses(
        missing_elective_courses or [], catalog
    )
    for name in ordered_elective_backfill:
        _place_one_course(
            name, "전공선택 학점이 아직 부족해 추천합니다.", catalog, schedule, taken,
            assigned_terms, remaining_terms, warnings, required_label="전공선택",
        )

    # 1.9단계: 산학프로젝트 인증 백필 — 1.75단계와 같은 이유로, 인증에 필요한 과목군
    # 중 course_reco.recommend_industry_project_backfill이 골라준 과목을 배치한다.
    ordered_industry_backfill = _topological_order_required_courses(
        missing_industry_project_courses or [], catalog
    )
    for name in ordered_industry_backfill:
        _place_one_course(
            name, "산학프로젝트 인증이 아직 부족해 추천합니다.", catalog, schedule, taken,
            assigned_terms, remaining_terms, warnings, required_label="산학프로젝트 인증",
        )

    # 2단계: 역량 격차 기반 전공선택 추천 — 1단계에서 이미 배치된 과목은 건너뛴다
    for reco in course_recommendations:
        name = reco["name"]
        if name in taken or name in assigned_terms:
            continue
        info = catalog.get(name)
        if info is None:
            warnings.append(f"'{name}'을(를) 교육과정 카탈로그에서 찾을 수 없습니다.")
            continue
        _place_one_course(
            name, reco.get("reason", ""), catalog, schedule, taken,
            assigned_terms, remaining_terms, warnings, required_label=None,
        )

    for reco in program_recommendations:
        if not remaining_terms:
            continue
        target_term = _target_term_for_program(reco, remaining_terms, schedule)
        schedule[target_term]["programs"].append({**reco, "is_precedent": True})

    return {"schedule": schedule, "warnings": warnings}
