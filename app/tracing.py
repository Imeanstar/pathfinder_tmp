"""분산 추적(Google Cloud Trace) — 운영 자동화 고도화(2026-08-24).

Cloud Run에 배포된 서비스 계정으로 자동 인증되는 GCP Cloud Trace로 요청 스팬을
보낸다(FastAPI 자동 계측 — 요청마다 메서드·경로·상태코드·소요시간이 스팬으로 남는다).

ENABLE_CLOUD_TRACE=true일 때만 켜진다(기본 꺼짐) — 로컬 개발·테스트 환경엔 GCP
인증정보가 없어 계속 켜두면 익스포터가 매 요청마다 인증을 시도하고, 337개 테스트
스위트가 매번 FastAPI 계측을 새로 거치게 만들 이유가 없다. Cloud Run 배포
(.github/workflows/deploy.yml)에서만 이 플래그를 켠다.

초기화 자체가 실패해도(패키지 문제·권한 문제 등) 앱은 그대로 뜬다 — "AI 경로엔
항상 대체 경로가 있어야 한다"는 이 프로젝트의 기존 원칙(app/llm.py,
app/retrieval.py, app/user_store.py)을 관측 가능성 계층에도 그대로 적용한다.
익스포터 자체(BatchSpanProcessor)도 export 실패를 백그라운드 스레드에서 조용히
삼키므로, 실제 GCP 인증이 안 되는 상황에서도(로컬에서 이 플래그를 실수로 켜도)
요청 처리 자체는 영향받지 않는다.
"""
import logging
import os

logger = logging.getLogger(__name__)


def setup_tracing(app) -> bool:
    """반환값: 실제로 계측이 켜졌는지(헬스체크·테스트용) — 스팬이 GCP까지 정상
    도달했는지는 보장하지 않는다(그건 BatchSpanProcessor가 백그라운드에서 처리)."""
    if os.environ.get("ENABLE_CLOUD_TRACE", "").strip().lower() not in ("true", "1"):
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.resourcedetector.gcp_resource_detector import (
            GoogleCloudResourceDetector,
        )
        from opentelemetry.sdk.resources import get_aggregated_resources
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = get_aggregated_resources([GoogleCloudResourceDetector()])
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app)
        logger.info("Cloud Trace 계측이 활성화됐습니다.")
        return True
    except Exception:
        logger.warning("Cloud Trace 초기화에 실패해 트레이싱 없이 계속 진행합니다.", exc_info=True)
        return False
