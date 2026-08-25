import numpy as np

from app.retrieval import GeminiEncoder, _fingerprint, _load_cached_embeddings, retrieve


def test_retrieve_courses_returns_nonempty_results_with_expected_shape():
    results = retrieve("자료구조", corpus="courses", top_k=3)
    assert len(results) > 0
    assert all({"doc", "score", "source"} <= result.keys() for result in results)
    assert results[0]["source"] == "courses"


def test_retrieve_yoram_returns_the_relevant_chunk_for_credit_query():
    results = retrieve("총 이수학점이 몇 학점이야", corpus="yoram", top_k=1)
    assert len(results) == 1
    assert "128학점" in results[0]["doc"]


def test_retrieve_programs_returns_nonempty_results():
    results = retrieve("프로그램", corpus="programs", top_k=3)
    assert len(results) > 0
    assert results[0]["source"] == "programs"


# --- 임베딩 사전계산 캐시 — 비용 최적화(2026-08-24) ---
# Cloud Run이 스케일-투-제로라, 트래픽 없다가 첫 요청이 올 때마다(콜드스타트)
# GeminiEncoder.fit()이 코퍼스 전체를 매번 Gemini API로 재임베딩했다. 미리 계산해
# data/embeddings/{corpus}.npz로 캐시해두면 코퍼스가 안 바뀐 한 API 호출 없이
# 그대로 로드만 한다 — 코퍼스가 바뀌면(계층 2 자동 PR 등) 지문이 안 맞아 자동으로
# 무시되고 실시간 계산으로 안전하게 폴백한다.


def test_fingerprint_is_deterministic_for_same_texts():
    texts = ["자료구조 3학점 전공필수", "알고리즘 3학점 전공필수"]
    assert _fingerprint(texts) == _fingerprint(texts)


def test_fingerprint_differs_when_texts_change():
    assert _fingerprint(["a", "b"]) != _fingerprint(["a", "c"])


def test_load_cached_embeddings_returns_none_when_cache_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("app.retrieval.EMBEDDINGS_CACHE_DIR", tmp_path)
    assert _load_cached_embeddings("courses", ["a", "b"]) is None


def test_load_cached_embeddings_returns_none_when_fingerprint_mismatches(tmp_path, monkeypatch):
    monkeypatch.setattr("app.retrieval.EMBEDDINGS_CACHE_DIR", tmp_path)
    np.savez(
        tmp_path / "courses.npz",
        embeddings=np.zeros((2, 4), dtype="float32"),
        fingerprint=np.array(_fingerprint(["old text"])),
    )
    # 캐시 저장 당시와 지금 텍스트가 다름(코퍼스가 바뀜) -> 무효화돼야 함
    assert _load_cached_embeddings("courses", ["new text"]) is None


def test_load_cached_embeddings_returns_array_when_fingerprint_matches(tmp_path, monkeypatch):
    monkeypatch.setattr("app.retrieval.EMBEDDINGS_CACHE_DIR", tmp_path)
    texts = ["자료구조", "알고리즘"]
    expected = np.array([[0.1, 0.2], [0.3, 0.4]], dtype="float32")
    np.savez(tmp_path / "courses.npz", embeddings=expected, fingerprint=np.array(_fingerprint(texts)))

    result = _load_cached_embeddings("courses", texts)

    assert result is not None
    np.testing.assert_array_equal(result, expected)


def test_gemini_encoder_uses_cache_without_calling_api(tmp_path, monkeypatch):
    monkeypatch.setattr("app.retrieval.EMBEDDINGS_CACHE_DIR", tmp_path)
    texts = ["자료구조", "알고리즘"]
    cached = np.array([[0.1, 0.2], [0.3, 0.4]], dtype="float32")
    np.savez(tmp_path / "courses.npz", embeddings=cached, fingerprint=np.array(_fingerprint(texts)))

    class ExplodingEmbeddings:
        def __init__(self, model):
            pass

        def embed_documents(self, texts):
            raise AssertionError("캐시가 있는데도 API를 호출함 — 캐시 로직이 안 먹었다")

    monkeypatch.setattr(
        "langchain_google_genai.GoogleGenerativeAIEmbeddings", ExplodingEmbeddings
    )

    encoder = GeminiEncoder(corpus="courses")
    encoder.fit(texts)

    np.testing.assert_array_equal(encoder._m, cached)


def test_gemini_encoder_falls_back_to_api_when_no_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("app.retrieval.EMBEDDINGS_CACHE_DIR", tmp_path)  # 빈 디렉토리 -> 캐시 없음
    texts = ["자료구조", "알고리즘"]

    class FakeEmbeddings:
        def __init__(self, model):
            pass

        def embed_documents(self, texts):
            return [[9.0, 9.0] for _ in texts]

    monkeypatch.setattr("langchain_google_genai.GoogleGenerativeAIEmbeddings", FakeEmbeddings)

    encoder = GeminiEncoder(corpus="courses")
    encoder.fit(texts)

    assert encoder._m.tolist() == [[9.0, 9.0], [9.0, 9.0]]


def test_make_encoder_passes_corpus_name_to_gemini_encoder(monkeypatch):
    # _CorpusIndex가 어느 코퍼스인지 몰라도 캐시를 찾을 방법이 없다 — make_encoder가
    # corpus를 그대로 GeminiEncoder에 전달해야 한다.
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    from app.retrieval import HybridEncoder, make_encoder

    encoder = make_encoder("courses")

    assert isinstance(encoder, HybridEncoder)
    gemini = [e for e in encoder.encoders if isinstance(e, GeminiEncoder)][0]
    assert gemini._corpus == "courses"
