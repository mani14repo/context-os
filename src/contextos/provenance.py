from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from contextos.library import ContextOS
from contextos.models import ContextNode

__all__ = [
    "ProvenanceEntry",
    "ProvenanceManifest",
    "build_provenance_manifest",
    "verify_provenance_manifest",
]


class ProvenanceEntry(BaseModel):
    version: int
    content_hash: str
    created_at: datetime
    updated_at: datetime


class ProvenanceManifest(BaseModel):
    node_id: UUID
    tenant_id: str
    entries: list[ProvenanceEntry]  # oldest to newest, current version last
    manifest_hash: str


def _hash_node(node: ContextNode) -> str:
    return hashlib.sha256(node.model_dump_json().encode("utf-8")).hexdigest()


def _hash_chain(hashes: list[str]) -> str:
    return hashlib.sha256("".join(hashes).encode("utf-8")).hexdigest()


async def build_provenance_manifest(
    context_os: ContextOS, tenant_id: str, node_id: UUID
) -> ProvenanceManifest:
    """Build a hash-chained manifest over a node's full version history (oldest to
    current). Uses the existing immutable-versioning system (`ContextOS.history()`)
    as its source of truth -- this doesn't add a new provenance-tracking subsystem,
    it makes the one that already exists (`put_node()` archiving prior versions)
    independently verifiable. Raises `KeyError` if the node doesn't exist for this
    tenant.
    """
    current = await context_os.store.get_node(tenant_id, node_id)
    if current is None:
        raise KeyError(node_id)
    history = await context_os.history(tenant_id, node_id)
    all_versions = [*history, current]
    entries = [
        ProvenanceEntry(
            version=version.version,
            content_hash=_hash_node(version),
            created_at=version.created_at,
            updated_at=version.updated_at,
        )
        for version in all_versions
    ]
    manifest_hash = _hash_chain([entry.content_hash for entry in entries])
    return ProvenanceManifest(
        node_id=node_id, tenant_id=tenant_id, entries=entries, manifest_hash=manifest_hash
    )


async def verify_provenance_manifest(context_os: ContextOS, manifest: ProvenanceManifest) -> bool:
    """Recompute a manifest from the current store state and compare hashes. If
    anything in the version history was altered outside of ContextOS's normal
    `put_node()` versioning (e.g. a direct database edit bypassing the library), the
    recomputed hash won't match and this returns False.
    """
    current = await build_provenance_manifest(context_os, manifest.tenant_id, manifest.node_id)
    return current.manifest_hash == manifest.manifest_hash
