"""RAG 코퍼스(요람/과목/프로그램)의 Gemini 임베딩을 미리 계산해 캐시 파일로 저장한다.

Cloud Run은 스케일-투-제로라, 트래픽 없다가 첫 요청이 올 때마다(콜드스타트)
GeminiEncoder.fit()이 코퍼스 전체를 매번 Gemini API로 재임베딩했다(2026-08-24 비용
최적화 작업 중 발견). 이 스크립트로 미리 계산해 커밋해두면, 코퍼스가 바뀌지 않는 한
서버는 API 호출 없이 그대로 로드만 한다.

코퍼스가 바뀌면(계층 2 자동 PR로 새 프로그램·요람이 반영되는 등) 지문(fingerprint)이
안 맞아 캐시가 자동으로 무시되고 실시간 계산으로 안전하게 폴백한다 — 다만 그 상태로
배포하면 다시 매번 재계산되므로, 코퍼스를 갱신할 때마다 이 스크립트를 다시 돌려
캐시를 갱신해야 한다.

실행: GOOGLE_API_KEY가 설정된 상태에서
  python3 data_pipeline/04_precompute_embeddings.py
출력: data/embeddings/{courses,programs,yoram}.npz
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np

from app.retrieval import CORPUS_SOURCES, EMBEDDINGS_CACHE_DIR, GeminiEncoder, _fingerprint, _load_corpus_items


def precompute(corpus: str) -> None:
    items = _load_corpus_items(corpus)
    texts = [it["_doc_text"] for it in items]

    encoder = GeminiEncoder()  # corpus를 안 넘겨 캐시를 안 보고 매번 실제로 새로 계산
    encoder.fit(texts)

    EMBEDDINGS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = EMBEDDINGS_CACHE_DIR / f"{corpus}.npz"
    np.savez(path, embeddings=encoder._m, fingerprint=np.array(_fingerprint(texts)))
    print(f"{corpus}: {len(texts)}건 임베딩 캐시 저장 -> {path} (차원 {encoder._m.shape[1]})")


if __name__ == "__main__":
    for corpus_name in CORPUS_SOURCES:
        precompute(corpus_name)
