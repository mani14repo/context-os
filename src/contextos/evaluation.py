from __future__ import annotations

import time
from collections.abc import Sequence
from uuid import UUID

from pydantic import BaseModel, Field

from contextos.library import ContextOS
from contextos.models import ContextRequest, MemoryType

__all__ = ["EvalCase", "EvalReport", "EvalResult", "run_eval_suite"]


class EvalCase(BaseModel):
    """A single retrieval-quality scenario: given this task, `assemble()` should
    return (roughly) these nodes. `expected_node_ids` empty means "nothing relevant
    should come back" -- a real, useful scenario for checking assemble() doesn't
    surface unrelated context for an off-topic task."""

    case_id: str
    tenant_id: str
    task: str
    agent: str = "eval-agent"
    expected_node_ids: set[UUID] = Field(default_factory=set)
    token_budget: int = Field(default=2000, ge=256)
    memory_scopes: set[MemoryType] = Field(default_factory=set)
    minimum_confidence: float = Field(default=0.0, ge=0, le=1)


class EvalResult(BaseModel):
    case_id: str
    precision: float
    recall: float
    f1: float
    returned_node_ids: list[UUID]
    missing_expected: list[UUID]
    token_count: int
    latency_seconds: float


class EvalReport(BaseModel):
    results: list[EvalResult]
    mean_precision: float
    mean_recall: float
    mean_f1: float
    mean_latency_seconds: float


def _mean(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


async def run_eval_suite(context_os: ContextOS, cases: Sequence[EvalCase]) -> EvalReport:
    """Run each EvalCase through `context_os.assemble()` and score retrieval quality.

    Precision/recall are computed against `ContextPackage.provenance` (the ids of
    nodes actually included in the assembled package, after ranking and budget
    fitting -- not just search() candidates). Framework-neutral: this only exercises
    `ContextOS.assemble()`, nothing LangGraph/MCP/A2A-specific, so it scores retrieval
    quality independent of whatever agent runtime is calling ContextOS.
    """
    results: list[EvalResult] = []
    for case in cases:
        start = time.perf_counter()
        package = await context_os.assemble(
            ContextRequest(
                tenant_id=case.tenant_id,
                task=case.task,
                agent=case.agent,
                token_budget=case.token_budget,
                memory_scopes=case.memory_scopes,
                minimum_confidence=case.minimum_confidence,
            )
        )
        latency = time.perf_counter() - start

        returned = set(package.provenance)
        true_positives = returned & case.expected_node_ids
        precision = (len(true_positives) / len(returned)) if returned else 1.0
        recall = (len(true_positives) / len(case.expected_node_ids)) if case.expected_node_ids else 1.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        results.append(
            EvalResult(
                case_id=case.case_id,
                precision=round(precision, 4),
                recall=round(recall, 4),
                f1=round(f1, 4),
                returned_node_ids=list(package.provenance),
                missing_expected=list(case.expected_node_ids - returned),
                token_count=package.token_count,
                latency_seconds=round(latency, 6),
            )
        )

    return EvalReport(
        results=results,
        mean_precision=_mean([r.precision for r in results]),
        mean_recall=_mean([r.recall for r in results]),
        mean_f1=_mean([r.f1 for r in results]),
        mean_latency_seconds=_mean([r.latency_seconds for r in results]),
    )
