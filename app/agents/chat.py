"""자유 질의 챗봇 — 성적표·진로·자기신고 정보와 요람/과목/아주허브 RAG 검색 결과를
근거로 Gemini가 답한다(2026-08-21, 사용자 요청).

`app/agents/session_chat.py`(슬롯필링: 어학·TOPCIT 두 질문만 정규식으로 처리)와는
완전히 다른 목적이다 — 저건 "성적표에 없는 값을 채우는" 절차이고, 이건 "이미 채운
정보를 근거로 자유롭게 물어보는" 대화다.

설계 원칙(이 프로젝트 전체와 동일):
- **사실 판단**(졸업요건 충족 여부, 특정 과목·학점·아주허브 프로그램이 실제로 있는지)은
  반드시 "참고 자료"에 있는 내용만 근거로 답한다. 참고 자료에 없는 사실을 지어내지 말고,
  확실하지 않으면 "정확한 내용은 학사팀에 문의하세요"라고 답한다.
- **일반 진로 상담**(어떤 자격증이 도움될지, 어떤 동아리·프로젝트를 해보면 좋을지 같은
  조언)은 참고 자료에 없어도 된다 — 우리 시스템은 자격증·동아리 데이터를 갖고 있지 않아
  이 범위까지 "근거 없으면 답하지 않는다"를 적용하면 아무 조언도 못 하게 된다. 이런
  질문엔 일반적인 지식으로 자유롭게 조언하되, 그게 학교 공식 정보가 아니라 참고용
  제안이라는 걸 자연스럽게 알 수 있게 답한다(예: "~같은 것도 도움이 될 수 있어요").
- API 키 없으면 거짓 답변 대신 정직하게 "지금은 안 됨"을 알린다.
- 자유 텍스트 입력이라 인젝션 방어(app/guardrail.py)를 성적표·프로젝트 제목과 동일하게 적용한다.
"""
import os
from typing import Callable

from app.guardrail import detect_injection, increment_blocked_count, is_guardrail_enabled
from app.prompts import get_prompt

RetrieveFn = Callable[..., list[dict]]
RewriteFn = Callable[[str, list[dict]], str]

# 프롬프트 원문은 app/prompts/*.yaml로 버전관리된다(2026-08-24) — 여기선 이름으로
# 최신 버전을 불러쓰기만 한다. 프롬프트를 고치려면 이 상수가 아니라 해당 yaml 파일의
# template을 고치고 version·changelog를 같이 올려야 한다(tests/test_prompt_registry.py).
REWRITE_QUERY_PROMPT = get_prompt("chat_query_rewrite")
SYSTEM_PROMPT = get_prompt("chat_system")


def _summarize_context(context: dict) -> str:
    from app.agents.competency import get_competency_label

    audit = context.get("audit", {})
    gap = context.get("gap", {})
    top_gaps = sorted(gap.items(), key=lambda kv: kv[1], reverse=True)[:5]
    gap_text = (
        ", ".join(f"{get_competency_label(k)}(격차 {v:.1f})" for k, v in top_gaps if v > 0) or "없음"
    )

    return (
        f"진로 트랙: {context.get('track')} ({context.get('track_type')})\n"
        f"총 이수학점: {audit.get('total_credit_earned')}\n"
        f"전공필수 완료: {audit.get('required_major_completed')}"
        f"(미이수: {', '.join(audit.get('missing_required_major_courses', [])) or '없음'})\n"
        f"전공선택 인증: {audit.get('elective_major_certified')}\n"
        f"산학프로젝트 인증: {audit.get('industry_project_certified')}\n"
        f"어학요건 충족: {audit.get('language_ok')}\n"
        f"프로그래밍역량 인증: {audit.get('programming_competency_certified')}\n"
        f"아직 확인 안 된 항목: {', '.join(audit.get('unresolved', [])) or '없음'}\n"
        f"역량 격차 상위: {gap_text}"
    )


def _retrieve_context_docs(message: str, retrieve_fn: RetrieveFn) -> str:
    blocks = []
    for corpus in ("yoram", "courses", "programs"):
        hits = retrieve_fn(message, corpus, top_k=2)
        for hit in hits:
            blocks.append(f"[{corpus}] {hit['doc']}")
    return "\n".join(blocks) if blocks else "(관련 자료를 찾지 못했습니다)"


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(없음)"
    role_label = {"user": "학생", "assistant": "챗봇"}
    return "\n".join(f"{role_label.get(h['role'], h['role'])}: {h['content']}" for h in history)


def rewrite_query(message: str, history: list[dict]) -> str:
    """검색용 질의만 바꾼다 — 실패하거나 키가 없으면 원문을 그대로 돌려준다(검색
    자체가 막히면 안 된다는 이 프로젝트의 '모든 AI 경로에 대체 경로' 원칙)."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return message
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        prompt = REWRITE_QUERY_PROMPT.format(history_text=_format_history(history), message=message)
        response = client.models.generate_content(model="gemini-3.6-flash", contents=prompt)
        rewritten = response.text.strip()
        return rewritten or message
    except Exception:
        return message


def answer_question(
    message: str,
    context: dict,
    history: list[dict],
    retrieve_fn: RetrieveFn | None = None,
    rewrite_fn: RewriteFn | None = None,
) -> dict:
    """반환값: {"reply": str, "blocked": bool}"""
    if is_guardrail_enabled() and detect_injection(message):
        increment_blocked_count()
        return {"reply": "입력에서 이상한 지시문이 감지되어 답변을 거부했습니다.", "blocked": True}

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {
            "reply": (
                "이 기능은 GOOGLE_API_KEY가 설정되어야 사용할 수 있습니다. "
                "지금은 화면1에서 입력한 정보로 계산된 졸업 현황만 확인할 수 있어요."
            ),
            "blocked": False,
        }

    if retrieve_fn is None:
        from app.retrieval import retrieve as retrieve_fn  # 지연 import(1차 프로젝트와 같은 패턴)
    if rewrite_fn is None:
        rewrite_fn = rewrite_query

    try:
        from google import genai

        # 검색은 재작성된 질의로, 최종 프롬프트의 "학생의 질문"은 원문 그대로 —
        # 챗봇이 재작성된 키워드투로 되묻듯 답하면 안 된다.
        search_query = rewrite_fn(message, history)
        client = genai.Client(api_key=api_key)
        prompt = SYSTEM_PROMPT.format(
            context_summary=_summarize_context(context),
            retrieved_docs=_retrieve_context_docs(search_query, retrieve_fn),
            history_text=_format_history(history),
            message=message,
        )
        response = client.models.generate_content(model="gemini-3.6-flash", contents=prompt)
        return {"reply": response.text.strip(), "blocked": False}
    except Exception:
        return {"reply": "답변 생성에 실패했습니다. 잠시 후 다시 시도해주세요.", "blocked": False}
