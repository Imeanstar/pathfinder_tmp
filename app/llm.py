"""
마스킹된 성적표 텍스트를 과목 리스트로 구조화하는 Gemini 호출 경계.

GOOGLE_API_KEY가 없으면(지금 개발 환경) 빈 리스트를 반환하는 스텁으로 대체한다 —
거짓 데이터를 지어내지 않는다(Task 3-1의 fail-closed 원칙과 같은 태도: 모를 땐
채우지 않고 비워둔다). 이 스텁을 쓸 때는 app/api.py가 응답에 경고를 같이 실어
프론트가 "개발 모드라 과목 인식을 건너뛰었다"는 걸 사용자에게 보여줄 수 있게 한다.

Gemini 호출은 유지보수 종료된 google-generativeai가 아니라 후속 SDK인
google-genai(`from google import genai`)를 쓴다 — 지연 import는 1차 프로젝트
(retrieval.py GeminiEncoder)와 같은 패턴.
"""
import json
import os

PROMPT_TEMPLATE = """다음은 마스킹된 대학교 성적표 텍스트다. 이수한 과목만 골라
JSON 배열로 출력하라. 각 항목은 {{"name": 과목명, "credit": 학점(숫자),
"category": 이수구분, "year": 수강년도(4자리 정수), "semester": 수강학기}} 형태여야 한다.

아주대학교 성적표는 이수구분이 다음 약어로 찍혀 있다. 약어를 아래 풀네임으로
반드시 변환해서 "category" 값으로 써라(약어 그대로 쓰지 마라):
- "전필" -> "전공필수"
- "전선" -> "전공선택"
- "전기" -> "전공기초" (주의: "전기공학"의 "전기"가 아니다. 전공기초는 SW커리어세미나·
  확률및통계1·선형대수1처럼 전공필수/전공선택과 별도인 이수구분이다. "전공선택"으로
  잘못 바꿔 쓰지 마라.)
- "교필" -> "교양필수"
- "교선" -> "교양선택"
- "일선" -> "일반선택"
위 6개 약어 외의 표기(전공필수/전공선택 등 이미 풀네임인 경우)는 그대로 쓰면 된다.

"year"는 그 과목 행의 "수강년도" 컬럼 값을 그대로 숫자로 옮겨 적어라(예: "2021 1학기"면
year는 2021).

"semester"는 같은 행의 "수강학기" 컬럼을 아래 세 값 중 정확히 하나로 정규화해서 써라:
- "1학기"
- "2학기"
- "계절학기" (원문이 "동계계절", "하계계절", "여름계절학기" 등 계절학기 표기이면 전부
  이 값 하나로 합쳐라 — 동계/하계를 구분하지 마라)

year 또는 semester를 알 수 없는 행은 통째로 건너뛰어라.

설명이나 다른 텍스트 없이 JSON 배열만 출력하라.

--- 성적표 텍스트 ---
{masked_text}
"""


def check_gemini_reachability() -> dict:
    """운영 자동화 계층 3(스모크 테스트, docs/superpowers/specs/2026-08-24-운영-자동화
    -design.md)이 Gemini 쿼터 초과·장애를 감지할 수 있도록 예외를 삼키지 않고 사유를
    그대로 보고한다 — default_structure_fn(빈 배열 폴백)·soften_recommendation_reasons
    (None 폴백)와 반대로, 이 함수의 존재 이유가 "실패를 정직하게 드러내는 것"이다.
    "ping" 한 단어짜리 최소 호출이라 토큰 소모가 거의 없다."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"reachable": False, "reason": "GOOGLE_API_KEY 미설정"}
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        client.models.generate_content(model="gemini-3.6-flash", contents="ping")
        return {"reachable": True}
    except Exception as e:
        return {"reachable": False, "reason": str(e)[:200]}


def default_structure_fn(masked_text: str) -> list[dict]:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return []
    return _call_gemini(masked_text, api_key)


def _call_gemini(masked_text: str, api_key: str) -> list[dict]:
    from google import genai

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=PROMPT_TEMPLATE.format(masked_text=masked_text),
    )
    text = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


REASON_PROMPT_TEMPLATE = """다음은 '{track_label}' 진로를 목표로 하는 학생에게 추천하는
과목·프로그램 목록이다. 각 항목마다 부드럽고 자연스러운 한국어 추천 멘트를 한 문장으로
새로 작성하라.

형식 예시(참고용, 그대로 베끼지 말고 자연스럽게 바꿔 쓸 것):
"{track_label}을(를) 목표로 하신다면, 이 과목을 통해 데이터베이스 역량을 기르는 건 어떨까요?"

지켜야 할 것:
- "'OO' 역량 격차가 커서 추천합니다" 같은 딱딱한 기계적 문구는 쓰지 마라.
- 항목 이름과 역량(reason에 이미 담긴 근거)은 아래 목록에 있는 그대로만 쓰고, 없는 내용을 지어내지 마라.
- 과목이면 "수강", 프로그램이면 "참여" 같은 자연스러운 동사를 골라라.

--- 항목 목록(JSON) ---
{items_json}

각 항목의 "name"을 그대로 key로 써서 다음 형식의 JSON 객체만 출력하라(설명 없이):
{{"항목명": "추천 멘트", ...}}
"""


def soften_recommendation_reasons(items: list[dict], track_label: str) -> dict[str, str] | None:
    """추천 사유를 부드러운 문장으로 다시 쓴다. 실패하면 None — 호출부가 원래의
    규칙기반 사유를 그대로 쓰게 한다(장식용 문구라 실패해도 추천 자체는 안전하게 유지됨).
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not items:
        return None
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        items_payload = [{"name": it["name"], "reason": it.get("reason", "")} for it in items]
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=REASON_PROMPT_TEMPLATE.format(
                track_label=track_label,
                items_json=json.dumps(items_payload, ensure_ascii=False),
            ),
        )
        text = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except Exception:
        return None
