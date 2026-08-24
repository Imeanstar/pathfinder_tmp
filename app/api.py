"""
FastAPI 앱 — 화면 4개가 호출하는 API. 여기서 처음 만들어졌다(docs/plans Task 5-4를
Task 5-1보다 앞당김: 백엔드가 이미 완성돼 있어 mock 화면을 먼저 만들었다가 나중에
실제 API로 갈아끼우는 것보다, API부터 실제로 붙이는 게 낫다고 판단, 2026-08-20).

무상태(stateless) 설계 — 서버가 세션을 저장하지 않는다(주제기획서.md 3-3 "저장은
브라우저 localStorage" 원칙과 동일선상). 매 요청마다 프론트가 이미 갖고 있는 상태
(과목 목록·트랙·설정)를 그대로 실어 보낸다.

PII 로깅 안전장치 (Task 3-1에서 이관됨): 이 파일 어디에서도 원본 PDF 바이트나
마스킹 전 텍스트를 로그·응답에 남기지 않는다. PiiLeakDetected/InjectionDetected
예외 메시지는 고정 문자열이라 원문이 섞일 수 없다(app/masking.py, app/parser.py 참고).
"""
import os
from dataclasses import asdict, replace
from typing import Optional

from dotenv import load_dotenv

load_dotenv()  # 프로젝트 루트 .env에서 GOOGLE_API_KEY 등을 읽는다(.gitignore 처리됨, Task 5-2~5-4 후속)

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agents.competency import (
    ManualProject,
    list_domain_overlays,
    list_grad_lab_clusters,
    list_project_fields,
    list_tracks,
)
from app.agents.chat import answer_question
from app.agents.session_chat import (
    apply_self_reported_answers,
    build_question_list,
    evaluate_language_score,
)
from app.agents.supervisor import run_full_plan
from app.audit import AuditResult, attach_citation, audit_graduation, load_requirements
from app.auth import InvalidDomainError, verify_google_id_token
from app.guardrail import get_blocked_count, is_guardrail_enabled, set_guardrail_override
from app.llm import default_structure_fn, soften_recommendation_reasons
from app.masking import PiiLeakDetected
from app.parser import (
    InjectionDetected,
    TranscriptData,
    compute_remaining_terms,
    compute_term_calendar_labels,
    find_low_credit_semesters,
    infer_admission_year,
    parse_transcript,
)
from app.retrieval import retrieve
from app.user_store import get_latest_plan, save_latest_plan

app = FastAPI(title="AJOU Pathfinder API")


@app.middleware("http")
async def _no_store_cache(request, call_next):
    """개발 서버라 정적 파일(JS/CSS)이 자주 바뀌는데, 브라우저가 예전 버전을 캐시해
    "코드를 고쳤는데도 화면이 그대로"인 혼란이 두 번 있었다(CSS 미적용, 챗봇 무반응처럼
    보였던 자기신고 로직 등) — 응답마다 캐시를 금지해 항상 최신 파일을 받게 한다."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response

DEFAULT_REMAINING_TERMS = ["2-2", "3-1", "3-2", "4-1", "4-2"]  # 2025학번 2학년 2학기 진입 기준

# 프론트가 Google Identity Services 버튼을 렌더링할 때 쓴다(app.auth의 검증용 audience와
# 같은 값이어야 함). Google Cloud Console에서 OAuth 2.0 클라이언트 ID(웹 애플리케이션)를
# 발급받아 .env에 채워야 실제로 로그인이 동작한다 — 없으면 /api/auth/verify가 정직하게
# 503을 돌려준다(GOOGLE_API_KEY 없을 때 "개발 모드"로 동작하는 것과 같은 원칙, 거짓
# 성공을 보여주지 않는다). os.environ을 매 요청 직접 읽어야 테스트에서 monkeypatch가 먹는다.


@app.get("/health")
def health():
    # GIT_SHA는 배포 시(docs/배포.md) --set-env-vars로 주입한다 — 운영 자동화 계층 3
    # (docs/superpowers/specs/2026-08-24-운영-자동화-design.md 4장)가 이 값과 main 최신
    # 커밋을 비교해 "배포본이 코드와 다른 상태"(버전 드리프트)를 감지한다. 로컬 개발처럼
    # 안 넘긴 환경에서는 거짓 버전을 지어내지 않고 정직하게 "unknown"을 반환한다.
    return {
        "status": "ok",
        "guardrail_enabled": is_guardrail_enabled(),
        "version": os.environ.get("GIT_SHA", "unknown"),
    }


@app.get("/api/guardrail")
def get_guardrail():
    return {"enabled": is_guardrail_enabled(), "blocked_count": get_blocked_count()}


@app.post("/api/guardrail/toggle")
def toggle_guardrail():
    """화면4 가드레일 스위치 — 서버 재시작 없이 즉시 켬/끔(app/guardrail.py 런타임 오버라이드)."""
    set_guardrail_override(not is_guardrail_enabled())
    return {"enabled": is_guardrail_enabled(), "blocked_count": get_blocked_count()}


@app.get("/api/config")
def config():
    """화면1 드롭다운(진로 목표/관심 산업/연구실 클러스터/개인 프로젝트 분야)이
    competency.yaml을 하드코딩하지 않고 여기서 받아 채우게 한다 — 온톨로지가
    바뀌어도 프론트를 따로 고칠 필요 없게."""
    return {
        "tracks": list_tracks(),
        "domain_overlays": list_domain_overlays(),
        "grad_lab_clusters": list_grad_lab_clusters(),
        "project_fields": list_project_fields(),
        "admission_year": 2025,  # MVP 대상 고정(주제기획서.md 5-1)
        "track_types": ["심화과정", "일반과정", "복수과정"],
        "google_client_id": os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""),
    }


class GoogleAuthRequest(BaseModel):
    credential: str  # Google Identity Services가 돌려주는 서명된 ID 토큰(JWT)


@app.post("/api/auth/verify")
def auth_verify(req: GoogleAuthRequest):
    """구글 로그인 — @ajou.ac.kr 계정만 허용(app/auth.py). 프론트가 보낸 이메일 문자열이
    아니라 구글 서명 검증을 통과한 토큰의 payload만 신뢰한다."""
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
    if not client_id:
        raise HTTPException(status_code=503, detail="구글 로그인이 아직 설정되지 않았습니다.")
    try:
        return verify_google_id_token(req.credential, client_id)
    except InvalidDomainError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception:
        raise HTTPException(status_code=401, detail="로그인 확인에 실패했습니다. 다시 시도해주세요.")


@app.get("/api/plan/latest/{email_hash}")
def plan_latest(email_hash: str):
    """[내 로드맵 이어보기] — 이 계정으로 가장 최근에 저장된 진단을 그대로 돌려준다.
    한 번도 진단한 적 없으면 없는 데이터를 지어내지 않고 404."""
    record = get_latest_plan(email_hash)
    if record is None:
        raise HTTPException(status_code=404, detail="저장된 로드맵이 없습니다.")
    return record


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    try:
        transcript = parse_transcript(pdf_bytes, structure_fn=default_structure_fn)
    except PiiLeakDetected:
        raise HTTPException(
            status_code=422,
            detail="자동 마스킹에 실패했습니다. 이름·학번 부분을 직접 가려서 다시 업로드해주세요.",
        )
    except InjectionDetected:
        raise HTTPException(
            status_code=422,
            detail="입력에서 이상한 지시문이 감지되어 처리를 거부했습니다.",
        )

    # 마스킹 본문은 앞부분만 잘라 보낸다 — 화면에서 "이렇게 가렸습니다"를 확인시키는 용도라
    # 전문이 필요하지 않고, 응답 크기도 불필요하게 키우지 않는다.
    response = {
        "courses": transcript.courses,
        "pii_masked": True,
        "masked_preview": transcript.masked_text[:1200],
        "admission_year": infer_admission_year(transcript.courses),
        "low_credit_semesters": find_low_credit_semesters(transcript.courses),
    }
    if not os.environ.get("GOOGLE_API_KEY"):
        response["warning"] = (
            "GOOGLE_API_KEY가 설정되지 않아 과목 인식을 건너뛰었습니다(개발 모드). "
            "화면에서 과목을 직접 입력해 테스트하세요."
        )
    return response


class ManualProjectIn(BaseModel):
    title: str
    field: str
    is_team: bool = False
    activity_type: str = "project"  # "project" | "club" | "certification" | "program"


class LanguageScoreIn(BaseModel):
    """화면1 어학 드롭다운 — exam은 graduation_requirements.json의 키와 같은 이름
    (TOEIC/TEPS/TOEFL_PBT/TOEFL_CBT/TOEFL_iBT/GTELP_Lv2/GTELP_Lv3/TOEIC_Speaking/OPIc).
    score는 점수제면 숫자, 등급제(TOEIC Speaking·OPIc)면 등급 문자열."""

    exam: str
    score: object


class ProgrammingCompetencyIn(BaseModel):
    topcit_score: Optional[int] = None
    apc_pass: bool = False
    contest_award: bool = False


class PlanRequest(BaseModel):
    courses: list[dict]
    admission_year: int = 2025
    track_type: str  # 심화과정 | 일반과정 | 복수과정
    track: str  # 8개 역할 트랙 중 하나
    domain_overlay: Optional[str] = None
    grad_lab_cluster: Optional[str] = None
    projects: list[ManualProjectIn] = []
    remaining_terms: list[str] = DEFAULT_REMAINING_TERMS
    # 화면1 마스킹 확인 단계에서 사용자가 "정규학기가 아닙니다"라고 답한 저학점
    # 학기만 담긴다(키: f"{year}-{semester}", 값 False). 나머지는 그대로 정규학기로
    # 간주한다(2026-08-22).
    irregular_semester_answers: dict[str, bool] = {}
    # 성적표에 없는 자기신고 항목 — 원래는 챗봇으로만 채웠으나, 화면1에서 드롭다운으로
    # 직접 고를 수 있게 되면서 여기서도 받는다(2026-08-21). 안 보내면 unresolved 유지.
    language_score: Optional[LanguageScoreIn] = None
    programming_competency: Optional[ProgrammingCompetencyIn] = None
    # 로그인한 계정의 "가장 최근 로드맵"을 자동 저장하는 데 쓴다(2026-08-21) — 로그인
    # 안 했으면 안 보내면 되고(None), 그러면 저장하지 않는다(기존 동작 그대로).
    email_hash: Optional[str] = None


def _apply_dropdown_selfreports(audit: AuditResult, req: "PlanRequest", requirements: dict) -> AuditResult:
    """화면1 드롭다운으로 직접 고른 어학·프로그래밍역량 값을 판정에 반영한다.

    챗봇(apply_self_reported_answers)은 자연어를 정규식으로 파싱하지만, 여기 오는 값은
    이미 구조화돼 있어 파싱 단계가 없다. 두 경로 모두 최종 판정은 같은 함수를 쓴다
    (evaluate_language_score / _evaluate_programming_competency).
    안 고른 항목은 건드리지 않는다 — unresolved가 그대로 남아 챗봇이 마저 물어본다.
    """
    language_ok = audit.language_ok
    programming_certified = audit.programming_competency_certified
    unresolved = list(audit.unresolved)

    if req.language_score is not None:
        evaluated = evaluate_language_score(
            req.language_score.exam, req.language_score.score, requirements
        )
        if evaluated is not None:
            language_ok = evaluated
            unresolved = [r for r in unresolved if r != "language_requirement"]

    if req.programming_competency is not None:
        pc = req.programming_competency
        cert = requirements["programming_competency_certification"]
        certified = (
            pc.topcit_score is not None and pc.topcit_score >= cert["topcit_min_score"]
        ) or pc.apc_pass or pc.contest_award
        programming_certified = certified
        unresolved = [r for r in unresolved if r != "programming_competency"]

    return replace(
        audit,
        language_ok=language_ok,
        programming_competency_certified=programming_certified,
        unresolved=unresolved,
    )


@app.post("/api/plan")
def plan(req: PlanRequest):
    resolved_admission_year = infer_admission_year(req.courses) or req.admission_year
    # "or" 폴백을 쓰면 안 된다 — compute_remaining_terms가 8개 정규학기를 모두 이수한
    # 학생에 대해 정확히 빈 리스트([], 남은 학기 없음)를 돌려줘도 파이썬은 []를 falsy로
    # 봐서 "계산 실패"로 오인해 req.remaining_terms(하드코딩된 기본값)로 되돌아간다
    # (2026-08-23 사용자 실사례 — 로드맵에 엉뚱한 연도의 5개 학기가 나타난 원인).
    # None(계산 불가, semester 정보 자체가 없음)일 때만 폴백해야 한다.
    computed_remaining_terms = compute_remaining_terms(req.courses, req.irregular_semester_answers)
    resolved_remaining_terms = (
        computed_remaining_terms if computed_remaining_terms is not None else req.remaining_terms
    )
    # 화면이 학기별 로드맵 카드에 실제 달력 연도를 붙여야 해서, "입학년도+학년" 공식이
    # 아니라 성적표에 실제로 찍힌 마지막 정규학기를 기준으로 계산한 라벨을 함께 보낸다
    # (2026-08-23 — 휴학한 학생은 입학년도+학년 공식이 실제 달력과 어긋난다).
    term_calendar_labels = compute_term_calendar_labels(
        req.courses, resolved_remaining_terms, req.irregular_semester_answers
    )
    transcript = TranscriptData(courses=req.courses)
    requirements = load_requirements(resolved_admission_year)
    audit = audit_graduation(transcript, resolved_admission_year, req.track_type, requirements)
    audit = _apply_dropdown_selfreports(audit, req, requirements)

    taken_course_names = {c["name"] for c in req.courses}
    projects = [
        ManualProject(title=p.title, field=p.field, is_team=p.is_team, activity_type=p.activity_type)
        for p in req.projects
    ]

    # 역량 격차(gap)가 자기신고로 다 채워져도 전공선택 학점·산학프로젝트 인증이 아직
    # 부족하면 로드맵에 그 졸업요건을 채울 과목이 추천돼야 한다(2026-08-23 사용자
    # 실사례 — gap 기반 추천만으론 이 두 요건이 로드맵에서 완전히 누락될 수 있었다).
    elective_threshold = requirements["elective_major_credit"][req.track_type]
    elective_credit_shortfall = max(0, elective_threshold - audit.elective_major_credit_earned)
    industry_min_courses = requirements["industry_project_certification"][req.track_type]["min_courses"]
    industry_project_shortfall = max(0, industry_min_courses - audit.industry_project_count)
    industry_project_course_groups = requirements["industry_project_certification"]["course_groups"]

    result = run_full_plan(
        transcript,
        projects,
        req.track,
        taken_course_names=taken_course_names,
        taken_program_titles=set(),
        remaining_terms=resolved_remaining_terms,
        domain_overlay=req.domain_overlay,
        grad_lab_cluster=req.grad_lab_cluster,
        missing_required_courses=audit.missing_required_major_courses,
        missing_major_foundation_courses=audit.missing_major_foundation_courses,
        elective_credit_shortfall=elective_credit_shortfall,
        industry_project_shortfall=industry_project_shortfall,
        industry_project_course_groups=industry_project_course_groups,
    )

    # 화면이 "33/42학점"처럼 기준치를 같이 보여줘야 해서, AuditResult엔 없는 원 기준값을
    # 별도로 실어 보낸다(요청 시점의 요람 원문 요건, requirements에서 그대로 뽑음).
    industry_cert = requirements["industry_project_certification"][req.track_type]
    requirements_summary = {
        "total_credit_required": requirements["total_credit"],
        "min_gpa": requirements["min_gpa"],
        "elective_major_credit_required": requirements["elective_major_credit"][req.track_type],
        "required_major_course_count": len(requirements["required_major_courses"]),
        "industry_project_min_courses": industry_cert["min_courses"],
        "language_requirement": requirements["language_requirement"],
        "elective_fieldwork_cap_credit": requirements.get("elective_credit_cap_groups", {})
        .get("현장실습군", {})
        .get("max_credit"),
    }
    major_foundation_threshold = requirements.get("major_foundation_credit", {}).get(req.track_type)
    if major_foundation_threshold is not None:
        requirements_summary["major_foundation_credit_required"] = major_foundation_threshold

    # "근거 보기" — 미이수 전공필수 과목마다 요람 조항을 검색해 붙인다(Task 3-2 attach_citation,
    # Task 3-4 retrieve 연결). yoram 코퍼스 전용 검색이라 LLM 호출 없음.
    citations = attach_citation(
        audit.missing_required_major_courses,
        search_fn=lambda query, corpus: retrieve(query, corpus, top_k=1),
    )

    # 추천 사유를 딱딱한 규칙기반 문구("'OO' 역량 격차가 커서 추천합니다")에서 부드러운
    # 자연어 멘트로 다시 쓴다(2026-08-21 사용자 요청). 실패/키없음이면 원문 그대로 둔다 —
    # 장식용 문구라 실패해도 추천 자체(closed-set)의 신뢰성엔 영향 없다.
    track_label = next((t["label"] for t in list_tracks() if t["id"] == req.track), req.track)
    recommended_items = result["course_recommendations"] + result["program_recommendations"]
    softened = soften_recommendation_reasons(recommended_items, track_label)
    if softened:
        for item in recommended_items:
            if item["name"] in softened:
                item["reason"] = softened[item["name"]]

    response = {
        "audit": asdict(audit),
        "admission_year": resolved_admission_year,
        "requirements_summary": requirements_summary,
        "citations": citations,
        "questions": build_question_list(audit.unresolved),
        "competency_vector": result["competency_vector"],
        "competency_target": result["competency_target"],
        "competency_evidence": result["competency_evidence"],
        "competency_levels": result["competency_levels"],
        "gap": result["gap"],
        "course_recommendations": result["course_recommendations"],
        "program_recommendations": result["program_recommendations"],
        "roadmap": result["roadmap"],
        "term_calendar_labels": term_calendar_labels,
    }

    if req.email_hash:
        save_latest_plan(req.email_hash, req.model_dump(mode="json"), response)

    return response


class SelfReportRequest(BaseModel):
    """대시보드 졸업 현황 카드의 "+ 추가하기" 인라인 폼용(2026-08-21) — 챗봇을 거치지
    않고 audit + 자기신고 값만 보내 갱신된 audit을 바로 받는다. 화면1의 구조화 드롭다운
    입력과 판정 로직을 그대로 재사용한다(_apply_dropdown_selfreports가 duck-typing으로
    language_score/programming_competency 속성만 보므로 PlanRequest와 그대로 호환)."""

    audit: dict
    admission_year: int = 2025
    language_score: Optional[LanguageScoreIn] = None
    programming_competency: Optional[ProgrammingCompetencyIn] = None


@app.post("/api/audit/selfreport")
def audit_selfreport(req: SelfReportRequest):
    requirements = load_requirements(req.admission_year)
    audit_result = AuditResult(**req.audit)
    updated = _apply_dropdown_selfreports(audit_result, req, requirements)
    return asdict(updated)


class ChatAnswerRequest(BaseModel):
    audit: dict
    answers: dict[str, str]
    admission_year: int = 2025


@app.post("/api/chat/answer")
def chat_answer(req: ChatAnswerRequest):
    requirements = load_requirements(req.admission_year)
    audit_result = AuditResult(**req.audit)
    updated = apply_self_reported_answers(audit_result, req.answers, requirements)
    return asdict(updated)


class ChatMessageIn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatAskRequest(BaseModel):
    message: str
    audit: dict
    gap: dict[str, float] = {}
    competency_vector: dict = {}
    track: str
    track_type: str
    history: list[ChatMessageIn] = []


@app.post("/api/chat/ask")
def chat_ask(req: ChatAskRequest):
    """자유 질의 챗봇 — 슬롯필링(/api/chat/answer)과 달리 정해진 질문이 아니라
    사용자가 뭐든 물어볼 수 있다(2026-08-21). 판정 데이터 + RAG 검색 결과를 근거로
    Gemini가 답하고, 근거가 없으면 학사팀 문의를 안내한다."""
    context = {
        "track": req.track,
        "track_type": req.track_type,
        "audit": req.audit,
        "gap": req.gap,
        "competency_vector": req.competency_vector,
    }
    history = [{"role": h.role, "content": h.content} for h in req.history]
    return answer_question(req.message, context, history)


@app.get("/")
def index():
    # 2026-08-21부터 진입점은 랜딩 페이지 — 여기서 [시작하기]를 눌러야 업로드로 넘어간다.
    return RedirectResponse(url="/index.html")


# 정적 파일(화면 HTML/CSS/JS) 서빙 — 반드시 API 라우트 전부 선언한 뒤 마지막에 마운트한다.
# 먼저 마운트하면 "/"가 모든 경로를 삼켜 위의 /api/* 라우트가 가려진다.
# 참고: 마운트 지점이 "/"라 HTML에서는 자산을 "/css/..","/js/.."로 참조한다("/static/.."가 아님 —
# 처음에 이 둘을 헷갈려 404가 났었다).
_STATIC_DIR = os.path.dirname(__file__) + "/static"
if os.path.isdir(_STATIC_DIR):
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
