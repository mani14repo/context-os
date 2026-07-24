"""Supersession, contradiction tracking, and tamper-evident provenance manifests.

No optional extras needed.

`contextos.workflows.supersede()` and `contradictions_for()` build on primitives that
already exist (edges, temporal validity) rather than adding a new subsystem:
superseding a node just ends its validity, so it drops out of `assemble()` the same
way any expired node does. `contextos.provenance` builds a hash-chained manifest over
a node's version history and can detect tampering that bypassed ContextOS entirely.
"""

import asyncio

from contextos import ContextEdge, ContextNode, ContextOS, MemoryType
from contextos.models import ContextQuery
from contextos.provenance import build_provenance_manifest, verify_provenance_manifest
from contextos.workflows import contradictions_for, supersede


async def main() -> None:
    context_os = ContextOS()

    # --- Supersession ---
    old_policy = await context_os.ingest(
        ContextNode(
            tenant_id="demo",
            node_type="policy",
            memory_type=MemoryType.SEMANTIC,
            title="Data retention policy",
            content="Working notes are retained for 30 days.",
            importance=0.8,
        )
    )
    new_policy = await context_os.ingest(
        ContextNode(
            tenant_id="demo",
            node_type="policy",
            memory_type=MemoryType.SEMANTIC,
            title="Data retention policy",
            content="Working notes are retained for 90 days.",
            importance=0.8,
        )
    )
    await supersede(context_os, "demo", new_node_id=new_policy.id, old_node_id=old_policy.id)

    results = await context_os.search(ContextQuery(tenant_id="demo", query="retention policy"))
    print(f"search() after supersession returns {len(results)} node(s):")
    for node in results:
        print(f"  - {node.content}")
    old_history = await context_os.history("demo", old_policy.id)
    print(f"Old policy's own history is untouched -- {len(old_history)} prior version(s) before it.")

    # --- Contradictions ---
    claim_a = await context_os.ingest(
        ContextNode(
            tenant_id="demo",
            node_type="finding",
            memory_type=MemoryType.EPISODIC,
            content="The DR test on 2026-06-01 succeeded.",
        )
    )
    claim_b = await context_os.ingest(
        ContextNode(
            tenant_id="demo",
            node_type="finding",
            memory_type=MemoryType.EPISODIC,
            content="The DR test on 2026-06-01 failed during Keycloak restoration.",
        )
    )
    await context_os.link(
        ContextEdge(
            tenant_id="demo", source_node_id=claim_a.id, target_node_id=claim_b.id, relationship="contradicts"
        )
    )
    conflicts = await contradictions_for(context_os, "demo", claim_a.id)
    print(f"\ncontradictions_for(claim_a) found {len(conflicts)} conflicting node(s):")
    for node in conflicts:
        print(f"  - {node.content}")

    # --- Provenance manifest ---
    claim_a.content = "The DR test on 2026-06-01 succeeded, per the initial report."
    await context_os.ingest(claim_a)
    manifest = await build_provenance_manifest(context_os, "demo", claim_a.id)
    print(f"\nProvenance manifest for claim_a: {len(manifest.entries)} version(s), hash={manifest.manifest_hash[:16]}...")
    print(f"verify_provenance_manifest() -> {await verify_provenance_manifest(context_os, manifest)}")

    # Simulate tampering that bypasses ContextOS entirely (direct store mutation).
    context_os.store.nodes[claim_a.id] = context_os.store.nodes[claim_a.id].model_copy(  # type: ignore[attr-defined]
        update={"content": "The DR test succeeded flawlessly with no issues whatsoever."}
    )
    print(
        f"After a direct (bypassing ContextOS) store mutation: "
        f"verify_provenance_manifest() -> {await verify_provenance_manifest(context_os, manifest)}"
    )


if __name__ == "__main__":
    asyncio.run(main())
