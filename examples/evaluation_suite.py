"""Score ContextOS.assemble()'s retrieval quality with the framework-neutral eval suite.

No optional extras needed -- contextos.evaluation only exercises ContextOS.assemble(),
independent of whatever agent runtime (LangGraph, MCP, A2A, or none) calls it.

Each EvalCase says "for this task, these node ids are the correct answer" (or, for the
third case, "nothing should come back"). run_eval_suite() runs assemble() for real and
scores precision/recall/f1 against what was actually returned -- and it surfaces a
real, honest finding here: precision comes out well below 1.0 on every case, including
the "off-topic" one, because `_rank()`'s score always includes `importance * 0.15`
(see contextos/orchestration/orchestrator.py), so a sufficiently important node can
clear the relevance bar for a nearly-unrelated task. Recall stays perfect because both
ingested nodes always get returned; it's precision that reveals the ranking isn't
selective enough on this small a corpus. That's the eval suite doing its job -- this
isn't a contrived pass/fail demo, it's what the numbers actually show.
"""

import asyncio

from contextos import ContextNode, ContextOS, MemoryType
from contextos.evaluation import EvalCase, run_eval_suite


async def main() -> None:
    context_os = ContextOS()

    release_note = await context_os.ingest(
        ContextNode(
            tenant_id="demo",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            title="Release convention",
            content="Stable releases use semantic versioning and include a changelog.",
            importance=0.9,
        )
    )
    dr_runbook = await context_os.ingest(
        ContextNode(
            tenant_id="demo",
            node_type="runbook",
            memory_type=MemoryType.OPERATIONAL,
            title="DR cutover runbook",
            content="The disaster recovery cutover is triggered manually by the on-call engineer.",
            importance=0.7,
        )
    )

    report = await run_eval_suite(
        context_os,
        [
            EvalCase(
                case_id="release-question",
                tenant_id="demo",
                task="What is required for a stable release?",
                expected_node_ids={release_note.id},
            ),
            EvalCase(
                case_id="dr-question",
                tenant_id="demo",
                task="How is the DR cutover triggered?",
                expected_node_ids={dr_runbook.id},
            ),
            EvalCase(
                case_id="off-topic-question",
                tenant_id="demo",
                task="What is the office coffee machine descaling schedule?",
                expected_node_ids=set(),
            ),
        ],
    )

    print(f"{'case':<20} {'precision':>10} {'recall':>8} {'f1':>8} {'tokens':>8} {'latency (ms)':>14}")
    for result in report.results:
        print(
            f"{result.case_id:<20} {result.precision:>10.2f} {result.recall:>8.2f} "
            f"{result.f1:>8.2f} {result.token_count:>8} {result.latency_seconds * 1000:>14.2f}"
        )
    print(
        f"\nmean precision={report.mean_precision:.2f} recall={report.mean_recall:.2f} "
        f"f1={report.mean_f1:.2f}"
    )
    print(
        "\nNote: precision < 1.0 even on the off-topic case is real, not a bug in this "
        "example -- both ingested nodes clear _rank()'s relevance bar on every task "
        "because importance alone contributes to the score. See the module docstring."
    )


if __name__ == "__main__":
    asyncio.run(main())
