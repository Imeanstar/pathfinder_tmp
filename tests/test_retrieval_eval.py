"""RAG 검색 품질 자동 평가 — 서비스 고도화(2026-08-24).

지금까지 "하이브리드 RAG"의 검색 품질은 문서(SECTION 8/15.1)에 수기로 적은 Q1~Q5
스팟체크가 전부였다 — 재현 가능한 자동 검증이 없었다. 여기서는 학생이 실제로 물어볼
법한 자연어 질문과, 그 답의 근거로 검색 결과 안에 반드시 있어야 하는 문자열(과목명·
요람 키워드)을 짝지어 pytest로 검증한다. 이 케이스들은 실제 코퍼스(data/*.json,
data/yoram_chunks.jsonl)로 직접 확인한 실측값이다 — 코퍼스가 바뀌거나 랭킹 로직이
바뀌어 품질이 떨어지면 이 테스트가 실패로 잡아낸다.

기존 tests/test_retrieval.py는 캐시·인코더 같은 내부 동작을 검증하고, 이 파일은
"검색이 실제로 쓸모 있는 결과를 주는가"만 본다 — 관심사가 달라 파일을 분리했다.
"""
import os

import pytest

from app.retrieval import _INDEX_CACHE, retrieve

# conftest.py의 _no_real_gemini_calls(autouse)가 모든 테스트에서 GOOGLE_API_KEY를 지운다
# (hermetic 기본값) — 그런데 이 파일의 목적 자체가 "실제 하이브리드(TF-IDF+Gemini) 검색
# 품질"을 확인하는 것이라, conftest.py가 안내한 대로("개별 테스트가 monkeypatch.setenv로
# 명시적으로 켜면 된다") 이 파일에서만 진짜 키를 되살린다. 값은 pytest가 이 모듈을
# import하는 시점(다른 테스트 모듈이 app.api를 먼저 import해 load_dotenv()가 이미
# 실행됐을 가능성이 높은 시점)에 한 번 캡처해둔다 — conftest 픽스처가 지우기 전 값이다.
_REAL_GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

requires_hybrid = pytest.mark.skipif(
    not _REAL_GOOGLE_API_KEY,
    reason="GOOGLE_API_KEY 없이는 TF-IDF 단독이라 의미 기반 검색 품질을 평가할 수 없음",
)


@pytest.fixture(autouse=True)
def _restore_real_key_and_reset_index_cache(monkeypatch):
    if _REAL_GOOGLE_API_KEY:
        monkeypatch.setenv("GOOGLE_API_KEY", _REAL_GOOGLE_API_KEY)
    # retrieve()는 코퍼스별 인덱스를 프로세스 전체에서 한 번만 만들어 재사용한다
    # (app/retrieval.py _INDEX_CACHE) — 다른 테스트 파일이 키 없는 상태로 먼저 만들어둔
    # TF-IDF 단독 인덱스를 그대로 물려받으면 안 되니, 이 파일 전후로 비워서 항상
    # 지금 이 시점의 키 상태에 맞게 다시 만들어지게 한다.
    _INDEX_CACHE.clear()
    yield
    _INDEX_CACHE.clear()


# (질문, 결과 top_k 안에 반드시 있어야 하는 문자열)
YORAM_CASES = [
    ("총 이수학점이 몇 학점이야", "128학점"),
    ("전공필수는 몇 과목 들어야 해", "전공필수"),
    ("영어 성적 기준이 뭐야", "TOEIC"),
    ("현장실습 학점은 몇 학점까지 인정돼", "현장실습"),
]

COURSE_CASES = [
    ("자료구조 배우고 싶어", "자료구조"),
    ("데이터베이스 관련 과목 추천해줘", "데이터베이스"),
    ("알고리즘 공부하려면 무슨 과목 들어야 해", "알고리즘"),
    ("클라우드 인프라 공부하려면 뭘 들어야 해", "클라우드_인프라"),
]

PROGRAM_CASES = [
    ("자동차 관련 프로그램 있어?", "미래자동차"),
]


@pytest.mark.parametrize("query,expected_substring", YORAM_CASES)
def test_yoram_retrieval_surfaces_expected_clause(query, expected_substring):
    results = retrieve(query, corpus="yoram", top_k=3)
    docs = [r["doc"] for r in results]
    assert any(expected_substring in doc for doc in docs), (
        f"'{query}' 검색 결과에 '{expected_substring}'이 없음: {[d[:80] for d in docs]}"
    )


@pytest.mark.parametrize("query,expected_substring", COURSE_CASES)
def test_course_retrieval_surfaces_expected_course(query, expected_substring):
    results = retrieve(query, corpus="courses", top_k=3)
    docs = [r["doc"] for r in results]
    assert any(expected_substring in doc for doc in docs), (
        f"'{query}' 검색 결과에 '{expected_substring}'이 없음: {[d[:80] for d in docs]}"
    )


@requires_hybrid
@pytest.mark.parametrize("query,expected_substring", PROGRAM_CASES)
def test_program_retrieval_surfaces_expected_program(query, expected_substring):
    # 이 케이스는 TF-IDF 단독으로는 못 찾는다("자동차"는 코퍼스 전체에서 흔한
    # "프로그램/강좌" 같은 고빈도 문자 n-gram에 묻힌다) — 의미 기반(Gemini 임베딩)
    # 없이는 사실상 실패하므로 하이브리드 모드에서만 돌린다.
    results = retrieve(query, corpus="programs", top_k=3)
    docs = [r["doc"] for r in results]
    assert any(expected_substring in doc for doc in docs), (
        f"'{query}' 검색 결과에 '{expected_substring}'이 없음: {[d[:80] for d in docs]}"
    )
