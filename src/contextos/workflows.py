from __future__ import annotations

from uuid import UUID

from contextos.library import ContextOS
from contextos.models import ContextEdge, ContextNode, utcnow

__all__ = ["contradictions_for", "supersede"]


async def supersede(
    context_os: ContextOS,
    tenant_id: str,
    *,
    new_node_id: UUID,
    old_node_id: UUID,
    relationship: str = "supersedes",
) -> ContextEdge:
    """Mark `new_node_id` as superseding `old_node_id`: creates a `supersedes` edge
    (new -> old) and ends the old node's temporal validity (`valid_to = now`), so it
    naturally drops out of `search()`/`assemble()` results the same way any expired
    node does -- via the validity enforcement that already exists, not new filtering
    logic. The old node is never deleted: provenance and version history stay intact
    (`ContextOS.history()`, `contextos.provenance.build_provenance_manifest()`).
    Calling this twice on an already-superseded node is a no-op on the node (its
    `valid_to` is left as-is) but still creates the new edge.
    """
    edge = await context_os.link(
        ContextEdge(
            tenant_id=tenant_id,
            source_node_id=new_node_id,
            target_node_id=old_node_id,
            relationship=relationship,
        )
    )
    old_node = await context_os.store.get_node(tenant_id, old_node_id)
    if old_node is not None and old_node.valid_to is None:
        old_node.valid_to = utcnow()
        await context_os.ingest(old_node)
    return edge


async def contradictions_for(
    context_os: ContextOS, tenant_id: str, node_id: UUID
) -> list[ContextNode]:
    """Nodes connected to `node_id` via a `contradicts` edge, in either direction.
    Doesn't resolve the contradiction (no automatic "which one is right" logic) --
    just surfaces it, so a caller (human reviewer, or a future authorization/
    governance layer) can decide.
    """
    edges = await context_os.edges_for(tenant_id, node_id)
    other_ids = {
        edge.target_node_id if edge.source_node_id == node_id else edge.source_node_id
        for edge in edges
        if edge.relationship == "contradicts"
    }
    nodes: list[ContextNode] = []
    for other_id in other_ids:
        node = await context_os.store.get_node(tenant_id, other_id)
        if node is not None:
            nodes.append(node)
    return nodes
