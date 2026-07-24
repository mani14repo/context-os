from __future__ import annotations

from datetime import datetime

from contextos.models import ContextNode, StorageTier, utcnow

RECENT_ACCESS_WINDOW_DAYS = 30


def suggest_tier(
    node: ContextNode, *, last_accessed: datetime | None, now: datetime | None = None
) -> StorageTier:
    """Suggest a storage tier for `node` from recency, importance, and metadata flags.

    Mirrors the simplified tiering rule from the design roadmap:
        active workflow                          -> hot
        accessed recently, or importance > 0.8   -> warm
        retention required                       -> cold
        otherwise                                -> archive

    `active_workflow` and `retention_required` are read from `node.metadata` since
    they're deployment-specific signals, not part of the stable domain model. Used by
    `ContextOS.apply_tiering_policy()`; this function itself has no side effects.
    """
    now = now or utcnow()
    if bool(node.metadata.get("active_workflow")):
        return StorageTier.HOT
    recently_accessed = (
        last_accessed is not None and (now - last_accessed).days <= RECENT_ACCESS_WINDOW_DAYS
    )
    if recently_accessed or node.importance > 0.8:
        return StorageTier.WARM
    if bool(node.metadata.get("retention_required")):
        return StorageTier.COLD
    return StorageTier.ARCHIVE
