from __future__ import annotations

from uuid import UUID


class LegalHoldError(Exception):
    """Raised by delete_node() when the node has `legal_hold=True`.

    Deletion under legal hold fails loudly rather than silently returning False --
    False from delete_node() already means "node not found or not this tenant's"; a
    held node existing but being blocked from deletion is a different, more
    consequential outcome and shouldn't be conflated with a not-found response.
    """

    def __init__(self, tenant_id: str, node_id: UUID) -> None:
        self.tenant_id = tenant_id
        self.node_id = node_id
        super().__init__(f"Node {node_id} (tenant {tenant_id!r}) is under legal hold and cannot be deleted")
