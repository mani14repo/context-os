"""Progressive retrieval: the smallest representation that answers the task.

ContextOS never stores just one copy of a node's content. Each node can carry up to
six progressive representations -- metadata, one-line, compact, detailed, full, and
original -- and `ContextOS.assemble()` automatically picks the smallest one that fits
the caller's token budget, falling back from `compact` to `one_line` when needed
(see `ContextOrchestrator._fit_budget`). This example shows both halves of that:
building the full compaction ladder for a node by hand, then watching `assemble()`
pick a different level of detail purely as a function of the token budget.
"""

import asyncio

from contextos import CompressionLevel, ContextNode, ContextOS, ContextRequest, MemoryType

RUNBOOK_CONTENT = (
    "The disaster recovery cutover begins the moment the on-call engineer receives "
    "three consecutive failed health checks from the primary region's load balancer, "
    "confirms the failure pattern against the regional status dashboard, escalates to "
    "the incident commander on rotation, opens a dedicated incident channel, pages the "
    "database, platform, and security teams in parallel, freezes all non-critical "
    "deployment pipelines across every affected service, and formally declares a "
    "regional disaster recovery event so every downstream runbook step becomes active. "
    "Once the event is declared, the database reliability team promotes the warm "
    "standby replica in the secondary region to primary by first pausing replication, "
    "verifying the replica's write-ahead log has fully caught up with the primary, "
    "running the standard promotion playbook that reassigns the primary DNS alias, "
    "updating the connection pooler configuration so every application node picks up "
    "the new primary within the next health check interval, and confirming through "
    "synthetic transactions that both reads and writes succeed against the newly "
    "promoted primary before signaling readiness to the platform team. "
    "With the database promoted, the platform team shifts production traffic "
    "gradually using weighted DNS records that move five percent of traffic every two "
    "minutes rather than all at once, watches error rates, latency percentiles, and "
    "saturation metrics on every downstream dashboard for regressions before allowing "
    "the shift to continue, confirms that the previously incomplete Keycloak "
    "restoration step now passes its full readiness probe including token issuance "
    "and session validation checks, and only proceeds to full cutover once every "
    "service on the standard checklist reports healthy for two consecutive monitoring "
    "intervals in a row without any manual intervention from the on-call rotation. "
    "The previous DR test failed on this exact Keycloak step. "
    "Once cutover completes, the team files an incident report within 24 hours."
)


async def main() -> None:
    context_os = ContextOS()
    node = await context_os.ingest(
        ContextNode(
            tenant_id="demo",
            node_type="runbook",
            memory_type=MemoryType.OPERATIONAL,
            title="DR cutover runbook",
            content=RUNBOOK_CONTENT,
            importance=0.8,
        )
    )

    print("=== Manual compaction ladder (ContextOS.compact) ===")
    for level in CompressionLevel:
        representation = await context_os.compact(node, level)
        print(f"{level.value:>10} ({representation.token_count:>3} tokens): {representation.content}")

    print("\n=== Budget-driven automatic selection (ContextOS.assemble) ===")
    # ContextRequest.token_budget has a floor of 256, so "tight" below still has to
    # beat that floor -- it works because this node's `compact` representation (three
    # dense sentences) is deliberately long enough to exceed 256 tokens on its own,
    # forcing assemble() to fall back to `one_line` instead.
    for label, budget in [("generous", 1000), ("tight", 256)]:
        package = await context_os.assemble(
            ContextRequest(
                tenant_id="demo",
                task="How does the DR cutover work?",
                agent="ops-assistant",
                token_budget=budget,
            )
        )
        if package.items:
            representation = package.items[0].node.representations[-1]
            print(
                f"{label:>17} budget={budget:>3}: picked '{representation.level.value}' "
                f"({representation.token_count} tokens) -> {representation.content}"
            )
        else:
            print(f"{label:>17} budget={budget:>3}: nothing fit -- {package.missing_context}")


if __name__ == "__main__":
    asyncio.run(main())
