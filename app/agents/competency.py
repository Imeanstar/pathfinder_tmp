"""
역량 진단 — 이수 과목(검증, 가중치 1.0) + 수기 프로젝트(자기신고, 가중치 0.5)를
competency.yaml 기준으로 합산한다. LLM 호출 없음(docs/plans Task 4-1).

출처를 분리해서 반환하는 이유: 화면 2가 검증/자기신고를 이중 바 그래프로 보여줘야
하고("클라우드·인프라 75% = 검증 60% + 자기신고 15%"), 평가에서 "자기신고를 어떻게
믿나요?"에 "가중치를 절반으로 두고 출처를 분리해 표시한다"고 답하기로 했기 때문
(주제기획서.md 3-3).
"""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.parser import TranscriptData

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data"

SELF_REPORT_WEIGHT = 0.5


@dataclass
class ManualProject:
    title: str
    field: str  # competency.yaml project_fields의 키 (예: "웹_백엔드", "기타")
    is_team: bool = False
    # 2026-08-21 추가, 2026-08-22 "동아리" 제거 + "수상 경력" 추가 — 역량 판정에 다양한
    # 근거(수업/실전 참여/자격증/수상 경력)를 반영하려면 활동 종류를 구분해야 했다.
    # "분야"(field)는 기존 project_fields를 그대로 재사용한다 — 자격증·수상 경력도
    # "이 활동이 어떤 역량 분야와 관련있는지"는 프로젝트와 같은 방식으로 태깅되면 되므로
    # 별도 매핑 테이블을 새로 만들 필요가 없었다.
    activity_type: str = "project"  # "project" | "program" | "certification" | "award"


@lru_cache(maxsize=1)
def _load_ontology() -> dict:
    path = ROOT / "data_pipeline" / "competency.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _load_course_tag_map() -> dict[str, list[str]]:
    """과목 카탈로그(data/courses.json)에서 과목명 -> competency_tags 매핑을 만든다.
    성적표(transcript)의 과목 dict 자체엔 태그가 없어 카탈로그와 대조해야 한다."""
    courses = json.loads((DATA_DIR / "courses.json").read_text(encoding="utf-8"))
    return {c["name"]: c.get("competency_tags", []) for c in courses}


def _empty_vector(competency_ids: list[str]) -> dict[str, dict[str, float]]:
    return {cid: {"verified": 0.0, "self_reported": 0.0} for cid in competency_ids}


def diagnose_competency(
    transcript: TranscriptData,
    projects: list[ManualProject],
    track: str,
) -> dict[str, dict[str, float]]:
    ontology = _load_ontology()
    competency_ids = [c["id"] for c in ontology["competencies"]]

    if track not in ontology["tracks"]:
        raise KeyError(f"알 수 없는 트랙: {track}")

    vector = _empty_vector(competency_ids)

    course_tags = _load_course_tag_map()
    for course in transcript.courses:
        for tag in course_tags.get(course["name"], []):
            if tag in vector:
                vector[tag]["verified"] += 1.0

    project_fields = ontology.get("project_fields", {})
    team_bonus = ontology.get("team_bonus", {})
    for project in projects:
        for tag, weight in project_fields.get(project.field, {}).items():
            if tag == "label" or tag not in vector:
                continue
            vector[tag]["self_reported"] += weight * SELF_REPORT_WEIGHT
        if project.is_team:
            for tag, weight in team_bonus.items():
                if tag in vector:
                    vector[tag]["self_reported"] += weight

    return vector


def collect_competency_evidence(
    transcript: TranscriptData, projects: list[ManualProject]
) -> dict[str, list[dict]]:
    """역량 축마다 "왜 이 점수인지"를 이수 과목·프로젝트 목록으로 보여준다.

    diagnose_competency()는 합산된 숫자만 반환해 "전부 충족"이 사용자에게 근거 없이
    보였다(2026-08-21 사용자 요청) — 같은 매핑 규칙을 다시 훑어 축마다 기여한 원본
    항목을 나열한다. 숫자 계산과 분리해 둬야 diagnose_competency의 track별 재계산과
    무관하게(트랙이 바뀌어도 "무엇을 근거로 했는지"는 그대로이므로) 캐시하기 쉽다.
    """
    evidence: dict[str, list[dict]] = {}

    course_tags = _load_course_tag_map()
    for course in transcript.courses:
        for tag in course_tags.get(course["name"], []):
            evidence.setdefault(tag, []).append({"type": "course", "name": course["name"]})

    ontology = _load_ontology()
    project_fields = ontology.get("project_fields", {})
    team_bonus = ontology.get("team_bonus", {})
    for project in projects:
        for tag in project_fields.get(project.field, {}):
            if tag == "label":
                continue
            evidence.setdefault(tag, []).append({"type": project.activity_type, "name": project.title})
        if project.is_team:
            for tag in team_bonus:
                evidence.setdefault(tag, []).append(
                    {"type": project.activity_type, "name": f"{project.title} (팀 활동 가산)"}
                )

    return evidence


# 5단계 역량 판정 — 2026-08-21 최초 설계, 2026-08-22 사용자 요청으로 점수 체계 재설계.
# "컴퓨터프로그래밍및실습 한 과목만 들었다고 소프트웨어공학·설계가 '충족'으로 뜨는 건
# 너무 낙관적이다"라는 지적에 따라, 연속적인 숫자 격차(gap) 대신 여러 근거를 합산한
# 점수로 5단계 라벨을 매긴다. compute_gap/compute_target의 연속값(레이더 모양·추천
# 랭킹에 계속 쓰임)은 건드리지 않고, 화면에 보여줄 라벨만 별도로 계산한다.
#
# 2026-08-22: "동아리"는 역량 근거로 부적절하다는 사용자 판단에 따라 제거하고 "수상
# 경력"을 추가했다. 또한 실전 참여·자격증·수상 경력을 O/X가 아니라 "몇 개/몇 회"
# 개수 기반 점수로 바꿨다(사용자 명시):
#   - 수업 이수율(0~1 비율) 그대로 최대 1점
#   - 자격증 1개당 0.5점
#   - 실전 참여(프로젝트·교내프로그램) 1회당 0.5점
#   - 수상 경력 1회당 1점
# 총점 구간(사용자 명시, 2.5점은 "만족"으로 확정):
#   0~0.5: 매우 부족 / 0.5 초과~1: 부족 / 1 초과~2: 보통 / 2 초과~2.5: 만족 / 2.5 초과: 매우 만족
_LEVEL_THRESHOLDS = [
    (0.5, "매우 부족"),
    (1.0, "부족"),
    (2.0, "보통"),
    (2.5, "만족"),
]


def _classify_level(score: float) -> str:
    for upper_bound, label in _LEVEL_THRESHOLDS:
        if score <= upper_bound:
            return label
    return "매우 만족"


@lru_cache(maxsize=1)
def _load_full_course_catalog() -> tuple[dict, ...]:
    return tuple(json.loads((DATA_DIR / "courses.json").read_text(encoding="utf-8")))


def _course_min_grade(course: dict) -> int:
    """과목의 권장 시기 중 가장 이른 학년. recommended_terms가 비어있으면(드묾)
    offered_terms로 대체한다."""
    terms = course.get("recommended_terms") or course.get("offered_terms") or ["1-1"]
    return min(int(t.split("-")[0]) for t in terms)


def _course_ratio_factor(axis: str, taken_names: set[str], current_grade: int, catalog: tuple[dict, ...]) -> float:
    """'수업' 요소 — 단순 O/X가 아니라 "지금 학년까지 커리큘럼상 들을 수 있는, 이 역량과
    관련된 전공필수 과목을 얼마나 이수했는가"의 비율(0~1)이다(2026-08-21 사용자 피드백:
    "n개 이상이냐 아니냐"조차 너무 거칠다 — 요람 커리큘럼표 기준 이수율로 봐야 한다).

    아직 권장 학년이 안 된 과목은 분모에서 뺀다 — "1학년인데 2학년 과목을 안 들었다"고
    감점하면 안 되기 때문. 관련 전공필수 과목 자체가 없는 역량(전공선택으로만 다뤄지는
    축)은 관련 과목(구분 무관) 이수 개수로 대체 판정한다(기존 방식과의 절충).
    """
    related_required = [
        c for c in catalog if c["category"] == "전공필수" and axis in c.get("competency_tags", [])
    ]
    if related_required:
        applicable = [c for c in related_required if _course_min_grade(c) <= current_grade]
        if not applicable:
            return 1.0  # 아직 평가 대상 아님 — 감점하지 않는다
        taken = [c for c in applicable if c["name"] in taken_names]
        return len(taken) / len(applicable)

    related_any = [c for c in catalog if axis in c.get("competency_tags", [])]
    related_taken_count = sum(1 for c in related_any if c["name"] in taken_names)
    return min(1.0, related_taken_count / 2)  # 2개 이상이면 만점 — 기존 임계값과 동일선상


def classify_competency_levels(
    evidence: dict[str, list[dict]],
    target: dict[str, float],
    current_grade: int = 4,
    course_catalog: list[dict] | tuple[dict, ...] | None = None,
) -> dict[str, dict]:
    """역량 축마다 {level, score, factors}를 반환한다. target<=0인(트랙과 무관한) 축은 제외.

    current_grade: 학생의 현재 학년(1~4). 커리큘럼상 아직 안 배운 과목으로 감점하지
    않기 위해 필요하다 — 기본값 4는 "정보 없으면 전 학년 커리큘럼을 기준으로 엄격하게
    본다"는 안전한 쪽(보수적) 기본값이다.
    course_catalog: 테스트에서 실제 data/courses.json에 안 묶이도록 하는 의존성 주입.
    """
    catalog = tuple(course_catalog) if course_catalog is not None else _load_full_course_catalog()
    levels = {}
    for axis, target_weight in target.items():
        if target_weight <= 0:
            continue
        items = evidence.get(axis, [])
        taken_names = {e["name"] for e in items if e["type"] == "course"}
        course_factor = _course_ratio_factor(axis, taken_names, current_grade, catalog)
        activity_count = sum(1 for e in items if e["type"] in ("project", "program"))
        certification_count = sum(1 for e in items if e["type"] == "certification")
        award_count = sum(1 for e in items if e["type"] == "award")
        factors = {
            "course": course_factor,
            "activity": activity_count,
            "certification": certification_count,
            "award": award_count,
        }
        score = course_factor + activity_count * 0.5 + certification_count * 0.5 + award_count * 1.0
        levels[axis] = {"level": _classify_level(score), "score": score, "factors": factors}
    return levels


def compute_target(track: str, overlay: dict[str, float] | None = None) -> dict[str, float]:
    """트랙이 요구하는 역량 목표치(오버레이 있으면 병합). 레이더 차트의 점선(목표)이 이 값이다.

    같은 역량 축을 트랙과 오버레이가 둘 다 가리키면 더 큰 쪽을 목표로 삼는다(단순 합산은
    두 축이 겹칠 때 목표치가 부풀려져 격차가 과장될 수 있어 피한다).

    compute_gap이 내부적으로 쓰던 계산을 별도 함수로 뺐다 — 화면이 gap만으로 목표를
    역산하면 이미 목표를 넘긴 축(gap=0)이 전부 "목표=현재"로 보여 레이더가 꽉 찬
    육각형이 되는 버그가 있었다(2026-08-21 실제 화면에서 발견).
    """
    ontology = _load_ontology()
    target = {k: v for k, v in ontology["tracks"][track].items() if k != "label"}
    if overlay:
        for competency_id, weight in overlay.items():
            if competency_id == "label":
                continue
            target[competency_id] = max(target.get(competency_id, 0.0), weight)
    return target


def compute_gap(
    competency_vector: dict[str, dict[str, float]],
    track: str,
    overlay: dict[str, float] | None = None,
) -> dict[str, float]:
    """목표(트랙 가중치, 오버레이 있으면 병합) - 현재 역량(검증+자기신고). 음수는 0으로 클램프."""
    target = compute_target(track, overlay)

    gap = {}
    for competency_id, target_weight in target.items():
        current = competency_vector.get(competency_id, {"verified": 0.0, "self_reported": 0.0})
        current_level = current["verified"] + current["self_reported"]
        gap[competency_id] = max(0.0, target_weight - current_level)
    return gap


def get_competency_label(competency_id: str) -> str:
    """역량 ID("커뮤니케이션_문서화")를 사람이 읽는 라벨("커뮤니케이션·문서화")로 바꾼다.
    추천 사유·챗봇 답변에 원본 ID가 언더바째로 그대로 노출되던 문제(2026-08-21 실사용
    중 발견) — competency.yaml에 이미 있던 label을 다른 모듈(app/agents/_reco_common.py,
    app/llm.py)도 재사용할 수 있게 공개 함수로 뺐다."""
    ontology = _load_ontology()
    for c in ontology["competencies"]:
        if c["id"] == competency_id:
            return c.get("label", competency_id)
    return competency_id.replace("_", "·")


def list_tracks() -> list[dict]:
    """화면1 '진로 목표' 드롭다운용 — 역할 트랙 8개를 {id, label}로."""
    ontology = _load_ontology()
    return [
        {"id": track_id, "label": data.get("label", track_id)}
        for track_id, data in ontology["tracks"].items()
    ]


def list_project_fields() -> list[dict]:
    """화면1 개인 프로젝트 '분야' 드롭다운용 — 9개 + 기타를 {id, label}로."""
    ontology = _load_ontology()
    return [
        {"id": field_id, "label": data.get("label", field_id)}
        for field_id, data in ontology["project_fields"].items()
    ]


def list_domain_overlays() -> list[str]:
    """산업 오버레이 이름 목록(화면1 2차 드롭다운용)."""
    return list(_load_ontology().get("domain_overlays", {}).keys())


def get_domain_overlay(name: str) -> dict[str, float]:
    return _load_ontology()["domain_overlays"][name]


def list_grad_lab_clusters() -> list[str]:
    """대학원_연구 트랙 선택 시 나타나는 연구실 클러스터 이름 목록."""
    return list(_load_ontology().get("grad_lab_clusters", {}).keys())


def get_grad_lab_cluster(name: str) -> dict[str, float]:
    return _load_ontology()["grad_lab_clusters"][name]
