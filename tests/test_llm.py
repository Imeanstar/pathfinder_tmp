from app.llm import PROMPT_TEMPLATE, _call_gemini, default_structure_fn


def test_prompt_template_category_enum_includes_major_foundation():
    # 요람상 전공기초(확률및통계1, SW커리어세미나 등)는 전공필수/전공선택과 별도
    # 영역인데, 프롬프트가 이 카테고리를 몰라 LLM이 "전공선택"으로 잘못 분류했다
    # (2026-08-22 실사용 버그 리포트 — 전공기초 학점이 전공선택 학점에 섞여 들어가
    # 일반과정 전공선택 10학점 기준이 미달인데도 충족으로 오판정될 수 있었다).
    assert "전공기초" in PROMPT_TEMPLATE


def test_prompt_template_maps_transcript_abbreviations_to_full_category_names():
    # 실제 아주대 성적표는 이수구분이 "전필/전선/전기/교필/교선/일선" 약어로 찍혀
    # 있다(성적표.pdf 실측 확인, 2026-08-22). 특히 "전기"는 "전기공학"과 혼동되기
    # 쉬워 프롬프트에 명시적으로 매핑을 알려줘야 한다.
    for abbr in ["전필", "전선", "전기", "교필", "교선", "일선"]:
        assert abbr in PROMPT_TEMPLATE
    assert "전기공학" in PROMPT_TEMPLATE  # 혼동하지 말라는 경고 문구가 있어야 함
    assert "일반선택" in PROMPT_TEMPLATE  # "일선" 대응 카테고리, 기존 enum엔 없었음


def test_prompt_template_requires_year_field_for_admission_year_inference():
    # 학번(admission_year)은 화면 입력이 아니라 성적표의 "수강년도" 최솟값으로
    # 서버가 자동 추론한다(1학년 1학기 휴학 불가 교칙 근거, 2026-08-22 사용자 지시).
    # 그러려면 과목마다 수강년도를 추출해야 한다.
    assert "year" in PROMPT_TEMPLATE
    assert "수강년도" in PROMPT_TEMPLATE


def test_prompt_template_requires_semester_field_normalized_to_three_values():
    # 남은 학기(8-n) 계산은 "수강학기"가 1학기/2학기/계절학기 중 뭔지 알아야 한다
    # (2026-08-22 사용자 요청 — 계절학기는 정규학기 카운트에서 항상 제외).
    assert "semester" in PROMPT_TEMPLATE
    assert "수강학기" in PROMPT_TEMPLATE
    assert "계절학기" in PROMPT_TEMPLATE


def test_default_structure_fn_returns_empty_list_without_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert default_structure_fn("자료구조 3학점 전공필수") == []


def test_call_gemini_parses_json_array_wrapped_in_code_fence(monkeypatch):
    class FakeResponse:
        text = '```json\n[{"name": "자료구조", "credit": 3, "category": "전공필수"}]\n```'

    class FakeModels:
        def generate_content(self, model, contents):
            return FakeResponse()

    class FakeClient:
        def __init__(self, api_key):
            self.models = FakeModels()

    monkeypatch.setattr("google.genai.Client", FakeClient)

    result = _call_gemini("마스킹된 성적표 텍스트", "fake-key")

    assert result == [{"name": "자료구조", "credit": 3, "category": "전공필수"}]


def test_soften_recommendation_reasons_returns_none_without_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    from app.llm import soften_recommendation_reasons

    items = [{"name": "데이터베이스", "reason": "'데이터베이스' 역량 격차가 커서 추천합니다."}]
    assert soften_recommendation_reasons(items, "백엔드 프로그래머") is None


def test_soften_recommendation_reasons_returns_none_for_empty_items(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    from app.llm import soften_recommendation_reasons

    assert soften_recommendation_reasons([], "백엔드 프로그래머") is None


def test_soften_recommendation_reasons_parses_json_map_from_gemini(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    class FakeResponse:
        text = '```json\n{"데이터베이스": "백엔드 프로그래머를 목표로 하신다면, 데이터베이스 과목으로 실무 역량을 다져보는 건 어떨까요?"}\n```'

    class FakeModels:
        def generate_content(self, model, contents):
            return FakeResponse()

    class FakeClient:
        def __init__(self, api_key):
            self.models = FakeModels()

    monkeypatch.setattr("google.genai.Client", FakeClient)

    from app.llm import soften_recommendation_reasons

    items = [{"name": "데이터베이스", "reason": "'데이터베이스' 역량 격차가 커서 추천합니다."}]
    result = soften_recommendation_reasons(items, "백엔드 프로그래머")

    assert result == {
        "데이터베이스": "백엔드 프로그래머를 목표로 하신다면, 데이터베이스 과목으로 실무 역량을 다져보는 건 어떨까요?"
    }


def test_soften_recommendation_reasons_returns_none_on_call_failure(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    class FailingClient:
        def __init__(self, api_key):
            raise RuntimeError("network error")

    monkeypatch.setattr("google.genai.Client", FailingClient)

    from app.llm import soften_recommendation_reasons

    items = [{"name": "데이터베이스", "reason": "..."}]
    assert soften_recommendation_reasons(items, "백엔드 프로그래머") is None
