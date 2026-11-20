import base64

import observability


def test_setup_langfuse_configures_private_otlp_export(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://jp.cloud.langfuse.com/")
    monkeypatch.setenv("LANGFUSE_TRACING_ENVIRONMENT", "test")
    monkeypatch.setenv("LANGFUSE_RELEASE", "test-release")

    monkeypatch.setenv("LOCAL_USER_ID", "local-user")
    provider = _FakeProvider()
    exporter_calls = []
    registration_calls = []

    monkeypatch.setattr(observability, "TracerProvider", lambda: provider)
    monkeypatch.setattr(observability, "BatchSpanProcessor", lambda exporter: ("processor", exporter))
    monkeypatch.setattr(
        observability,
        "OTLPSpanExporter",
        lambda **kwargs: exporter_calls.append(kwargs) or "exporter",
    )
    monkeypatch.setattr(
        observability,
        "set_tracer_provider",
        lambda *args, **kwargs: registration_calls.append((args, kwargs)),
    )

    assert observability.setup_langfuse("room-123") is provider
    expected_auth = base64.b64encode(b"pk-lf-test:sk-lf-test").decode()
    assert exporter_calls == [
        {
            "endpoint": "https://jp.cloud.langfuse.com/api/public/otel/v1/traces",
            "headers": {
                "Authorization": f"Basic {expected_auth}",
                "x-langfuse-ingestion-version": "4",
            },
        }
    ]
    assert provider.processors[0][0] == "processor"
    assert provider.processors[0][1].exporter == "exporter"
    assert registration_calls == [
        (
            (provider,),
            {
                "metadata": {
                    "langfuse.session.id": "room-123",
                    "langfuse.environment": "test",
                    "service.name": "care-support-voice-agent",
                    "langfuse.user.id": "local-user",
                    "langfuse.observation.metadata.content_policy": "redacted",
                    "langfuse.release": "test-release",
                },
                "allow_pii": False,
            },
        )
    ]


def test_setup_langfuse_skips_missing_configuration(monkeypatch):
    for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"):
        monkeypatch.delenv(name, raising=False)

    assert observability.setup_langfuse("room-123") is None


def test_setup_langfuse_obeys_disable_flag(monkeypatch):
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "false")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")

    assert observability.setup_langfuse("room-123") is None


def test_flush_traces():
    provider = _FakeProvider()
    assert observability.flush_traces(provider) is True
    assert provider.flush_count == 1


class _FakeProvider:
    def __init__(self):
        self.processors = []
        self.flush_count = 0

    def add_span_processor(self, processor):
        self.processors.append(processor)

    def force_flush(self):
        self.flush_count += 1
        return True
