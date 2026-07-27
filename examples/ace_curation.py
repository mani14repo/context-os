"""ACE-style Curator loop: de-duplicate and reinforce insights instead of piling
up near-identical bullets.

No optional extras needed.

The ACE paper (Zhang et al., 2025, arxiv.org/abs/2510.04618) frames context
adaptation as an evolving "playbook": a Generator produces reasoning traces, a
Reflector distills lessons from them, and a Curator either merges a lesson into an
existing bullet (if it's a restatement of something already known) or appends it
as new. This example plays out that Curator step against a stream of candidate
insights a Reflector might produce across several agent runs -- some genuinely
new, some restating a lesson already in the playbook -- using
`contextos.curation.curate()`, which composes `find_similar()` (grow-and-refine
de-duplication via embedding similarity) and `ContextOS.record_feedback()` (the
helpful/harmful counters ACE tracks per bullet).

The default `HashingEmbeddingProvider` is lexical-hash-based, not a real semantic
model -- it catches near-identical rewordings (the kind an LLM reflecting on
similar failures tends to produce) but not loose paraphrases with little word
overlap. The insights below are written close enough in wording to demonstrate
that honestly; swap in a real EmbeddingProvider for genuine paraphrase detection.
"""

import asyncio

from contextos import ContextNode, ContextOS, MemoryType
from contextos.curation import curate
from contextos.models import ContextQuery

_TENANT = "agent-playbook"

# A Reflector distilling lessons from several agent runs. Insights 1/3/6 are the
# same underlying lesson (retry 429s with backoff) reworded across runs; 2/5 are
# likewise the same pagination lesson said twice. 4 is genuinely new. This mirrors
# how an agent often re-derives a lesson it already learned, rather than the
# playbook growing by one redundant bullet every time that happens.
_CANDIDATE_INSIGHTS = [
    "Tool calls that fail with a 429 should be retried with exponential backoff, not treated as a hard failure.",
    "The email API paginates results -- check for a next_page_token before assuming the list is complete.",
    "A 429 response means retry with exponential backoff, not a hard failure.",
    "Writes to /tmp are not persisted across tool calls -- write output files to the workspace directory instead.",
    "Check for a next_page_token on the email API before assuming the results list is complete.",
    "On a 429, retry with exponential backoff rather than treating it as a hard failure.",
]


async def main() -> None:
    context_os = ContextOS()

    for round_number, insight_text in enumerate(_CANDIDATE_INSIGHTS, start=1):
        candidate = ContextNode(
            tenant_id=_TENANT, node_type="playbook_bullet", memory_type=MemoryType.PROCEDURAL, content=insight_text
        )
        before = len(await context_os.search(ContextQuery(tenant_id=_TENANT, query="", max_results=50)))
        await curate(context_os, _TENANT, candidate, merge_threshold=0.5)
        after = len(await context_os.search(ContextQuery(tenant_id=_TENANT, query="", max_results=50)))
        outcome = "merged into existing bullet" if after == before else "added as new bullet"
        print(f"Round {round_number} ({outcome}):\n  \"{insight_text}\"")

    playbook = await context_os.search(ContextQuery(tenant_id=_TENANT, query="", max_results=50))
    print(f"\nFinal playbook: {len(playbook)} bullet(s) from {len(_CANDIDATE_INSIGHTS)} candidate insights.")
    for node in sorted(playbook, key=lambda n: n.metadata.get("feedback_helpful_count", 0), reverse=True):
        reinforcements = node.metadata.get("feedback_helpful_count", 0)
        print(f"  [reinforced {reinforcements}x] {node.content}")


if __name__ == "__main__":
    asyncio.run(main())
