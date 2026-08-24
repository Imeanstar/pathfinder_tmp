"""분산 추적(Google Cloud Trace) — 운영 자동화 고도화(2026-08-24).

ENABLE_CLOUD_TRACE 플래그로만 켜진다는 것과, 켜졌든 꺼졌든 앱이 절대 죽지 않는다는
것(이 프로젝트 전체의 "AI/인프라 경로엔 항상 대체 경로가 있어야 한다" 원칙)을
검증한다. 실제 Cloud Trace로 스팬이 나가는지는 GCP 인증정보가 있어야 확인 가능한
영역이라 여기선 다루지 않는다 — 이 파일의 관심사는 "이 서비스가 로컬/CI(GCP 인증정보
없음)에서도 절대 깨지지 않는가"다.
"""
from fastapi import FastAPI

from app.tracing import setup_tracing


def test_setup_tracing_is_noop_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_CLOUD_TRACE", raising=False)
    app = FastAPI()

    enabled = setup_tracing(app)

    assert enabled is False


def test_setup_tracing_noop_values_do_not_enable(monkeypatch):
    app = FastAPI()
    for value in ("false", "0", "off", ""):
        monkeypatch.setenv("ENABLE_CLOUD_TRACE", value)
        assert setup_tracing(app) is False


def test_setup_tracing_never_raises_even_without_gcp_credentials(monkeypatch):
    """로컬 개발·CI엔 GCP 서비스 계정이 없다 — CloudTraceSpanExporter 초기화나
    인증이 실패해도 setup_tracing()이 예외를 던져 앱 기동 자체를 막으면 안 된다."""
    monkeypatch.setenv("ENABLE_CLOUD_TRACE", "true")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    app = FastAPI()

    setup_tracing(app)  # 예외 없이 끝나야 한다(반환값이 True든 False든 둘 다 정상)


def test_setup_tracing_returns_true_when_instrumentation_succeeds(monkeypatch):
    """실제 GCP 인증 없이도 FastAPIInstrumentor.instrument_app까지는 성공할 수 있다
    (익스포터 인증 실패는 백그라운드 BatchSpanProcessor에서 조용히 실패함) — 그 흐름을
    흉내내려고 CloudTraceSpanExporter 생성만 목으로 대체한다. shutdown/export까지
    갖춘 목을 써야 인터프리터 종료 시 TracerProvider.shutdown()이 조용히 넘어간다."""

    class FakeExporter:
        def export(self, spans):
            return None

        def shutdown(self):
            return None

        def force_flush(self, timeout_millis=30000):
            return True

    monkeypatch.setenv("ENABLE_CLOUD_TRACE", "true")
    monkeypatch.setattr(
        "opentelemetry.exporter.cloud_trace.CloudTraceSpanExporter", FakeExporter
    )
    app = FastAPI()

    assert setup_tracing(app) is True
