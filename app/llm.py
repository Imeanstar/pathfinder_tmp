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

from app.prompts import get_prompt

# 프롬프트 원문은 app/prompts/*.yaml로 버전관리된다(2026-08-24) — 여기선 이름으로
# 최신 버전을 불러쓰기만 한다. 프롬프트를 고치려면 이 상수가 아니라 해당 yaml 파일의
# template을 고치고 version·changelog를 같이 올려야 한다(tests/test_prompt_registry.py).
PROMPT_TEMPLATE = get_prompt("transcript_extraction")


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


REASON_PROMPT_TEMPLATE = get_prompt("recommendation_reason")


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
