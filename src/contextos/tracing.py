from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

try:
    from opentelemetry import trace as _otel_trace
except ImportError:
    _otel_trace = None  # type: ignore[assignment]

_TRACER_NAME = "contextos"


class _NoOpSpan:
    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass


_NOOP_SPAN = _NoOpSpan()


@contextmanager
def start_span(name: str, **attributes: Any) -> Iterator[Any]:
    """Start an OpenTelemetry span, or do nothing if opentelemetry isn't installed.

    Safe to call unconditionally from core ContextOS code without adding a hard
    dependency: opentelemetry-api's global tracer is itself a no-op when no SDK is
    configured, and this falls back further to a no-op span (same `set_attribute`
    interface) when the `opentelemetry` package (the "otel" extra) isn't installed at
    all. Either way, calling code doesn't need to check whether tracing is active --
    see ContextOS.ingest()/assemble()/etc. for how the built-in operations use it.
    """
    if _otel_trace is None:
        yield _NOOP_SPAN
        return
    tracer = _otel_trace.get_tracer(_TRACER_NAME)
    with tracer.start_as_current_span(name, attributes=attributes) as span:
        yield span
