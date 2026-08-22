import pytest

from app.agents.competency import (
    classify_competency_levels,
    collect_competency_evidence,
    ManualProject,
    compute_gap,
    compute_target,
    diagnose_competency,
    get_domain_overlay,
    get_grad_lab_cluster,
    list_domain_overlays,
    list_grad_lab_clusters,
    list_project_fields,
    list_tracks,
)
from app.parser import TranscriptData


def test_diagnose_competency_counts_verified_from_taken_courses():
    # data/courses.json에서 "자료구조"는 competency_tags=["자료구조_알고리즘"]로 태깅되어 있음(Task 2-4)
    transcript = TranscriptData(courses=[{"name": "자료구조", "credit": 3, "category": "전공필수"}])
    result = diagnose_competency(transcript, projects=[], track="백엔드")
    assert result["자료구조_알고리즘"]["verified"] == 1.0
    assert result["웹_프론트엔드"]["verified"] == 0.0


def test_diagnose_competency_ignores_unmatched_course_names():
    transcript = TranscriptData(courses=[{"name": "존재하지않는과목", "credit": 3, "category": "전공선택"}])
    result = diagnose_competency(transcript, projects=[], track="백엔드")
    assert all(v["verified"] == 0.0 for v in result.values())


def test_diagnose_competency_applies_project_field_weight_with_self_report_discount():
    transcript = TranscriptData(courses=[])
    project = ManualProject(title="배달앱 클론 코딩", field="웹_백엔드", is_team=False)
    result = diagnose_competency(transcript, projects=[project], track="백엔드")
    # competency.yaml project_fields.웹_백엔드: {클라우드_인프라:0.6, 데이터베이스:0.5, 시스템_네트워크:0.3}
    # 자기신고 기본 가중치 0.5를 곱한다(설계: 검증 1.0 vs 자기신고 0.5)
    assert result["클라우드_인프라"]["self_reported"] == pytest.approx(0.6 * 0.5)
    assert result["데이터베이스"]["self_reported"] == pytest.approx(0.5 * 0.5)
    assert result["클라우드_인프라"]["verified"] == 0.0  # 자기신고는 verified를 건드리지 않음


def test_diagnose_competency_adds_team_bonus_for_team_projects():
    transcript = TranscriptData(courses=[])
    project = ManualProject(title="해커톤", field="웹_백엔드", is_team=True)
    result = diagnose_competency(transcript, projects=[project], track="백엔드")
    # team_bonus(협업_PM:0.5, 커뮤니케이션_문서화:0.3)는 이미 가산치로 설계된 값이라 추가 할인 없이 더한다
    assert result["협업_PM"]["self_reported"] == pytest.approx(0.5)
    assert result["커뮤니케이션_문서화"]["self_reported"] == pytest.approx(0.3)


def test_diagnose_competency_기타_필드는_LLM_없이_기여하지_않음():
    transcript = TranscriptData(courses=[])
    project = ManualProject(title="자유 주제 프로젝트", field="기타", is_team=False)
    result = diagnose_competency(transcript, projects=[project], track="백엔드")
    assert all(v["self_reported"] == 0.0 for v in result.values())


def test_diagnose_competency_returns_all_sixteen_competencies():
    # 13(기술) + 3(도메인 지식: 금융·핀테크/모빌리티·임베디드/공공정책·행정) = 16 (2026-08-20 개정)
    transcript = TranscriptData(courses=[])
    result = diagnose_competency(transcript, projects=[], track="백엔드")
    assert len(result) == 16


def test_diagnose_competency_raises_on_unknown_track():
    transcript = TranscriptData(courses=[])
    with pytest.raises(KeyError):
        diagnose_competency(transcript, projects=[], track="존재하지않는트랙")


def test_compute_gap_returns_target_minus_current_when_positive():
    vector = {"데이터베이스": {"verified": 0.0, "self_reported": 0.0}}
    gap = compute_gap(vector, track="백엔드")
    assert gap["데이터베이스"] == pytest.approx(0.9)  # competency.yaml 백엔드.데이터베이스 가중치


def test_compute_gap_is_zero_when_current_meets_or_exceeds_target():
    vector = {"데이터베이스": {"verified": 2.0, "self_reported": 0.0}}
    gap = compute_gap(vector, track="백엔드")
    assert gap["데이터베이스"] == 0.0


def test_compute_gap_skips_the_label_key_present_on_some_tracks():
    # AI_데이터/기획_PM/대학원_연구는 track dict에 'label' 문자열 키가 섞여 있다(경쟁·매핑용이 아님)
    gap = compute_gap({}, track="AI_데이터")
    assert "label" not in gap


def test_compute_gap_merges_domain_overlay_adding_new_domain_axis():
    overlay = get_domain_overlay("금융권")
    gap = compute_gap({}, track="백엔드", overlay=overlay)
    assert gap["금융_핀테크지식"] == pytest.approx(0.9)  # 역할 트랙엔 없던 축이 오버레이로 추가됨


def test_compute_gap_merge_takes_max_when_both_track_and_overlay_weight_same_axis():
    overlay = {"보안": 0.4}  # 백엔드 트랙 자체도 보안: 0.4
    gap_with_overlay = compute_gap({}, track="백엔드", overlay=overlay)
    gap_without_overlay = compute_gap({}, track="백엔드")
    assert gap_with_overlay["보안"] == gap_without_overlay["보안"]  # 겹치면 낮은 쪽에 끌려가지 않음


def test_list_domain_overlays_returns_all_three():
    assert set(list_domain_overlays()) == {"금융권", "자동차", "공공기관"}


def test_get_domain_overlay_returns_named_weights():
    overlay = get_domain_overlay("자동차")
    assert overlay["모빌리티_임베디드지식"] == pytest.approx(0.9)


def test_list_grad_lab_clusters_returns_all_five():
    assert len(list_grad_lab_clusters()) == 5


def test_get_grad_lab_cluster_returns_named_weights():
    cluster = get_grad_lab_cluster("AI_데이터_연구실")
    assert cluster["데이터_ML"] == pytest.approx(0.9)


def test_list_tracks_returns_eight_role_tracks_with_id_and_label():
    tracks = list_tracks()
    assert len(tracks) == 8
    ids = {t["id"] for t in tracks}
    assert "백엔드" in ids and "시스템_네트워크_엔지니어" in ids and "SW아키텍트" in ids
    backend = next(t for t in tracks if t["id"] == "백엔드")
    assert backend["label"] == "백엔드 프로그래머"


def test_list_project_fields_returns_nine_plus_기타_with_id_and_label():
    fields = list_project_fields()
    assert len(fields) == 10  # 9개 + 기타
    ids = {f["id"] for f in fields}
    assert "기타" in ids
    web_backend = next(f for f in fields if f["id"] == "웹_백엔드")
    assert web_backend["label"] == "웹 백엔드"


def test_compute_target_returns_track_weights_for_radar():
    """레이더 차트가 '목표 대비 현재'를 그리려면 목표치 자체가 필요하다.
    지금까지는 gap(=목표-현재, 0클램프)만 내려줘서 프론트가 '현재+gap'으로 역산했는데,
    이미 목표를 넘긴 축은 gap이 0이라 목표가 현재와 같아 보이는 문제가 있었다
    (2026-08-21 실제 화면에서 육각형이 꽉 찬 채로 나오는 버그로 발견)."""
    target = compute_target("백엔드")

    assert target["데이터베이스"] > 0
    assert "label" not in target  # label은 표시용 메타데이터라 역량 축이 아니다


def test_compute_target_merges_overlay_with_max():
    """오버레이가 같은 축을 가리키면 compute_gap과 동일하게 큰 쪽을 목표로 삼아야 한다."""
    base = compute_target("대학원_연구")
    merged = compute_target("대학원_연구", overlay=get_grad_lab_cluster("AI_데이터_연구실"))

    assert merged["데이터_ML"] >= base["데이터_ML"]
    assert merged["데이터_ML"] > 0.5  # 클러스터(0.9)가 대학원 트랙 기본(0.5)보다 크다


def test_collect_competency_evidence_lists_contributing_courses_and_projects():
    """레이더의 '충족' 판정이 어떤 과목·프로젝트 때문인지 사용자가 확인할 수 있어야 한다
    (2026-08-21 사용자 요청 — 근거 없이 전부 충족으로만 뜨면 신뢰할 수 없다)."""
    transcript = TranscriptData(courses=[
        {"name": "자료구조", "credit": 3, "category": "전공필수"},
        {"name": "운영체제", "credit": 3, "category": "전공필수"},
    ])
    projects = [ManualProject(title="배달앱 클론", field="웹_백엔드", is_team=True)]

    evidence = collect_competency_evidence(transcript, projects)

    course_names = {e["name"] for e in evidence["자료구조_알고리즘"]}
    assert "자료구조" in course_names
    assert all(e["type"] == "course" for e in evidence["자료구조_알고리즘"])

    # 웹_백엔드 project_field는 클라우드_인프라/데이터베이스/시스템_네트워크에 기여하고,
    # 팀 프로젝트라 team_bonus(협업_PM/커뮤니케이션_문서화)도 별도로 붙는다
    assert any(e["type"] == "project" and e["name"] == "배달앱 클론" for e in evidence["클라우드_인프라"])
    assert any("배달앱 클론" in e["name"] for e in evidence["협업_PM"])


def test_collect_competency_evidence_empty_for_untouched_axis():
    transcript = TranscriptData(courses=[])
    evidence = collect_competency_evidence(transcript, projects=[])
    assert evidence.get("보안", []) == []


# --- 역량 진단 재설계 2차: '수업' 요소를 이진(O/X) 판정이 아니라 커리큘럼상
# "지금 학년까지 들을 수 있는 관련 전공필수 과목 이수율"로 계산한다 (2026-08-21
# 사용자 피드백 — "n개 이상 들었냐 아니냐"는 여전히 너무 거칠다는 지적).
# 실제 courses.json에 안 묶이도록 course_catalog를 의존성 주입한다(이 프로젝트
# 전반의 관례 — structure_fn/select_fn과 같은 패턴).

FAKE_CATALOG = [
    {"name": "이산수학", "category": "전공필수", "recommended_terms": ["2-1"], "competency_tags": ["자료구조_알고리즘"]},
    {"name": "자료구조", "category": "전공필수", "recommended_terms": ["2-1"], "competency_tags": ["자료구조_알고리즘"]},
    {"name": "알고리즘", "category": "전공필수", "recommended_terms": ["2-2"], "competency_tags": ["자료구조_알고리즘"]},
    {"name": "데이터베이스", "category": "전공선택", "recommended_terms": ["3-1"], "competency_tags": ["데이터베이스"]},
    {"name": "데이터마이닝", "category": "전공선택", "recommended_terms": ["3-2"], "competency_tags": ["데이터베이스"]},
]


def test_classify_competency_levels_course_factor_is_a_ratio_not_boolean():
    """관련 전공필수 3개 중 1개만 이수 → '수업' 요소는 O/X가 아니라 1/3 비율이어야 한다
    (2026-08-21 — "n개 들었냐 아니냐"는 여전히 너무 거칠다는 지적을 반영)."""
    evidence = {"자료구조_알고리즘": [{"type": "course", "name": "이산수학"}]}
    target = {"자료구조_알고리즘": 0.8}

    levels = classify_competency_levels(evidence, target, current_grade=2, course_catalog=FAKE_CATALOG)

    assert levels["자료구조_알고리즘"]["factors"]["course"] == pytest.approx(1 / 3)


def test_classify_competency_levels_excludes_courses_not_yet_reached_by_grade():
    """알고리즘은 2학년2학기 권장인데 아직 1학년이면(current_grade=1) 평가 대상에서
    빠져야 한다 — 아직 들을 시기가 안 된 과목 때문에 감점하면 안 된다."""
    evidence = {"자료구조_알고리즘": [{"type": "course", "name": "이산수학"}, {"type": "course", "name": "자료구조"}]}
    target = {"자료구조_알고리즘": 0.8}

    levels = classify_competency_levels(evidence, target, current_grade=1, course_catalog=FAKE_CATALOG)

    # 1학년까지 권장되는 관련 전공필수 과목이 하나도 없다 -> 아직 평가 대상 아님 -> 만점(1.0) 처리
    assert levels["자료구조_알고리즘"]["factors"]["course"] == 1.0


def test_classify_competency_levels_full_required_completion_scores_full_course_factor():
    evidence = {"자료구조_알고리즘": [
        {"type": "course", "name": "이산수학"}, {"type": "course", "name": "자료구조"},
        {"type": "course", "name": "알고리즘"},
    ]}
    target = {"자료구조_알고리즘": 0.8}

    levels = classify_competency_levels(evidence, target, current_grade=3, course_catalog=FAKE_CATALOG)

    assert levels["자료구조_알고리즘"]["factors"]["course"] == 1.0


def test_classify_competency_levels_falls_back_to_course_count_when_no_required_mapping():
    """전공필수 매핑이 없는 역량(예: 데이터베이스는 전공선택만 있음)은 관련 과목
    이수 개수로 대체 판정한다 — 기존 방식과의 절충."""
    evidence = {"데이터베이스": [{"type": "course", "name": "데이터베이스"}, {"type": "course", "name": "데이터마이닝"}]}
    target = {"데이터베이스": 0.5}

    levels = classify_competency_levels(evidence, target, current_grade=4, course_catalog=FAKE_CATALOG)

    assert levels["데이터베이스"]["factors"]["course"] == 1.0


def test_classify_competency_levels_combines_course_ratio_with_other_three_factors():
    """수업 요소(연속값)와 실전참여·자격증(0.5점/개)·수상경력(1점/개)을 합산해 최종
    점수를 낸다(2026-08-22 재설계 — 동아리 제거, 수상 경력 추가, O/X 대신 개수 기반
    점수제로 변경)."""
    evidence = {"자료구조_알고리즘": [
        {"type": "course", "name": "이산수학"},  # 1/3
        {"type": "project", "name": "토이프로젝트"},  # 실전 참여 1회 -> 0.5
        {"type": "certification", "name": "정보처리기사"},  # 자격증 1개 -> 0.5
        {"type": "award", "name": "해커톤 수상"},  # 수상 경력 1회 -> 1.0
    ]}
    target = {"자료구조_알고리즘": 0.8}

    levels = classify_competency_levels(evidence, target, current_grade=2, course_catalog=FAKE_CATALOG)
    result = levels["자료구조_알고리즘"]

    assert result["score"] == pytest.approx(1 / 3 + 0.5 + 0.5 + 1.0)
    assert result["level"] == "만족"  # 2 < 2.333 <= 2.5


def test_classify_competency_levels_program_participation_counts_as_activity():
    """교내 프로그램 참여도 '실전 참여' 요소로 인정된다(프로젝트와 동일 취급).
    실전 참여는 이제 O/X가 아니라 횟수(1회당 0.5점)다."""
    evidence = {"데이터베이스": [{"type": "program", "name": "AWS 부트캠프"}]}
    target = {"데이터베이스": 0.6}

    levels = classify_competency_levels(evidence, target, current_grade=4, course_catalog=FAKE_CATALOG)

    assert levels["데이터베이스"]["factors"]["activity"] == 1
    assert levels["데이터베이스"]["score"] == pytest.approx(0.5)


def test_classify_competency_levels_certification_count_scores_half_point_each():
    evidence = {"데이터베이스": [
        {"type": "certification", "name": "정보처리기사"},
        {"type": "certification", "name": "SQLD"},
    ]}
    levels = classify_competency_levels(
        evidence, {"데이터베이스": 0.6}, current_grade=4, course_catalog=FAKE_CATALOG
    )
    assert levels["데이터베이스"]["factors"]["certification"] == 2
    assert levels["데이터베이스"]["score"] == pytest.approx(1.0)


def test_classify_competency_levels_award_count_scores_one_point_each():
    evidence = {"데이터베이스": [
        {"type": "award", "name": "교내 해커톤 대상"},
        {"type": "award", "name": "공모전 입상"},
    ]}
    levels = classify_competency_levels(
        evidence, {"데이터베이스": 0.6}, current_grade=4, course_catalog=FAKE_CATALOG
    )
    assert levels["데이터베이스"]["factors"]["award"] == 2
    assert levels["데이터베이스"]["score"] == pytest.approx(2.0)


def test_classify_competency_levels_club_evidence_no_longer_contributes_score():
    # 동아리는 더 이상 역량 판정 요소가 아니다(2026-08-22 사용자 요청) — evidence에
    # club 항목이 있어도 factors에 "club" 키 자체가 없고 점수에도 기여하지 않는다.
    evidence = {"데이터베이스": [{"type": "club", "name": "데이터 분석 동아리"}]}
    levels = classify_competency_levels(
        evidence, {"데이터베이스": 0.6}, current_grade=4, course_catalog=FAKE_CATALOG
    )
    assert levels["데이터베이스"]["score"] == 0
    assert "club" not in levels["데이터베이스"]["factors"]


@pytest.mark.parametrize(
    "activity_count,expected_score,expected_level",
    [
        (0, 0.0, "매우 부족"),
        (1, 0.5, "매우 부족"),   # 경계값: 0.5는 매우 부족(사용자 명시)
        (2, 1.0, "부족"),        # 경계값: 1.0은 부족
        (3, 1.5, "보통"),
        (4, 2.0, "보통"),        # 경계값: 2.0은 보통
        (5, 2.5, "만족"),        # 경계값: 2.5는 만족(사용자 확인)
        (6, 3.0, "매우 만족"),
    ],
)
def test_classify_competency_levels_boundary_thresholds(activity_count, expected_score, expected_level):
    # 과목 근거가 전혀 없는 축(course_factor=0)에서 실전 참여 횟수만으로 점수 경계를
    # 정확히 테스트한다(1회당 0.5점, 0.5 단위로 정확히 떨어짐).
    evidence = {"웹_프론트엔드": [
        {"type": "project", "name": f"프로젝트{i}"} for i in range(activity_count)
    ]}
    levels = classify_competency_levels(
        evidence, {"웹_프론트엔드": 0.5}, current_grade=4, course_catalog=FAKE_CATALOG
    )
    result = levels["웹_프론트엔드"]
    assert result["score"] == pytest.approx(expected_score)
    assert result["level"] == expected_level


def test_classify_competency_levels_skips_axes_with_zero_target():
    evidence = {"보안": [{"type": "course", "name": "정보보호개론"}]}
    target = {"보안": 0.0, "데이터베이스": 0.5}

    levels = classify_competency_levels(evidence, target, current_grade=4, course_catalog=FAKE_CATALOG)

    assert "보안" not in levels
    assert "데이터베이스" in levels


def test_classify_competency_levels_no_evidence_is_매우_부족():
    levels = classify_competency_levels({}, {"데이터베이스": 0.4}, current_grade=4, course_catalog=FAKE_CATALOG)
    assert levels["데이터베이스"]["score"] == 0
    assert levels["데이터베이스"]["level"] == "매우 부족"


def test_collect_competency_evidence_tags_activity_type_from_manual_project():
    """자격증·수상경력·교내프로그램도 project_fields를 '분야' 선택지로 재사용하되,
    근거 표시에는 실제 활동 유형(activity_type)이 그대로 남아야 한다
    (2026-08-21 — 역량 판정이 과목 존재만으로 결정되지 않도록 다양한 근거를 받기 위함.
    2026-08-22: 동아리 대신 수상 경력으로 예시 교체)."""
    activities = [
        ManualProject(title="정보처리기사", field="웹_백엔드", activity_type="certification"),
        ManualProject(title="교내 해커톤 대상", field="웹_백엔드", activity_type="award"),
        ManualProject(title="AWS 클라우드 스쿨", field="웹_백엔드", activity_type="program"),
    ]
    evidence = collect_competency_evidence(TranscriptData(courses=[]), activities)

    types_by_name = {e["name"]: e["type"] for e in evidence["클라우드_인프라"]}
    assert types_by_name["정보처리기사"] == "certification"
    assert types_by_name["교내 해커톤 대상"] == "award"
    assert types_by_name["AWS 클라우드 스쿨"] == "program"


def test_manual_project_activity_type_defaults_to_project():
    project = ManualProject(title="배달앱 클론", field="웹_백엔드")
    assert project.activity_type == "project"
