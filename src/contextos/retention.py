from __future__ import annotations

from datetime import datetime

from contextos.models import ContextNode, utcnow

__all__ = ["is_eligible_for_deletion"]


def is_eligible_for_deletion(node: ContextNode, *, now: datetime | None = None) -> bool:
    """Whether `ContextOS.apply_retention_policy()` should delete this node:
    `retention_until` has passed and `legal_hold` is not set. `legal_hold` always
    wins, regardless of `retention_until` -- a node can be simultaneously past its
    retention deadline and legally held, and legal obligations take precedence.
    `retention_until=None` means "no deletion deadline configured" -- never eligible.
    """
    if node.legal_hold:
        return False
    if node.retention_until is None:
        return False
    return node.retention_until <= (now or utcnow())
