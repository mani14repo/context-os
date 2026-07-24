"""OpenTelemetry tracing for ContextOS's core operations.

Requires: pip install -e ".[otel]"

contextos.tracing.start_span() wraps ContextOS.ingest()/link()/compact()/move()/
apply_tiering_policy() and ContextOrchestrator.assemble() -- it's called
unconditionally from core code, but it's a genuine no-op until an application
configures an OpenTelemetry SDK and exporter, exactly how opentelemetry-api is meant
to be used as a library dependency (no hard dependency on the SDK, no behavior change
if the caller never sets one up). This example configures the simplest possible
exporter -- spans printed to the console, synchronously, as each one ends -- so you
can see exactly what gets traced and with what attributes.
"""

import asyncio

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from contextos import ContextNode, ContextOS, ContextRequest, MemoryType, StorageTier


def configure_tracing() -> None:
    provider = TracerProvider()
    # SimpleSpanProcessor exports each span synchronously as soon as it ends -- right
    # for a short-lived script; a real service would use BatchSpanProcessor plus a
    # real backend exporter (OTLP, etc.) instead of ConsoleSpanExporter.
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)


async def main() -> None:
    configure_tracing()

    context_os = ContextOS()

    print("--- ingest() span ---")
    node = await context_os.ingest(
        ContextNode(
            tenant_id="demo",
            node_type="project_convention",
            memory_type=MemoryType.SEMANTIC,
            title="Release convention",
            content="Stable releases use semantic versioning and include a changelog.",
            importance=0.9,
        )
    )

    print("\n--- assemble() span (note contextos.item_count/token_count attributes) ---")
    await context_os.assemble(
        ContextRequest(
            tenant_id="demo",
            task="What is required for a stable release?",
            agent="release-assistant",
            token_budget=500,
        )
    )

    print("\n--- move() span ---")
    await context_os.move("demo", node.id, StorageTier.COLD)


if __name__ == "__main__":
    asyncio.run(main())
