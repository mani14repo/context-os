from __future__ import annotations

from contextos.models import ContextPackage

__all__ = ["to_prompt_context"]


def to_prompt_context(package: ContextPackage) -> str:
    """Flatten a ContextPackage into a prompt-ready string for a LangGraph node.

    ContextOS.assemble() already does the retrieval, ranking, and budget-fitting a
    LangGraph node needs -- this is the one piece of glue an LLM prompt actually
    requires beyond that: turning structured `RankedContext` items into text. There
    is intentionally no other LangGraph-specific machinery here; build state graphs
    directly against `ContextOS.assemble()`/`ContextOS.ingest()` as shown in
    examples/langgraph_integration.py.
    """
    if not package.items:
        return "No relevant context found."
    lines = []
    for item in package.items:
        representation = item.node.representations[-1] if item.node.representations else None
        content = representation.content if representation else (item.node.summary or item.node.title)
        lines.append(f"- ({item.node.memory_type.value}) {content or ''}".rstrip())
    return "\n".join(lines)
