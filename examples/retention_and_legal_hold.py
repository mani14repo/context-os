"""Retention rules and legal hold.

No optional extras needed.

Two governance primitives on ContextNode: `retention_until` (an eligibility deadline
for deletion) and `legal_hold` (an override that blocks deletion regardless of the
deadline). `ContextOS.apply_retention_policy()` sweeps a tenant's nodes and deletes
whatever is past its deadline and not held; `ContextOS.delete()` raises
`LegalHoldError` (not a silent no-op) if you try to delete a held node directly.
"""

import asyncio
from datetime import timedelta

from contextos import ContextNode, ContextOS, MemoryType
from contextos.errors import LegalHoldError
from contextos.models import utcnow


async def main() -> None:
    context_os = ContextOS()

    expired_note = await context_os.ingest(
        ContextNode(
            tenant_id="demo",
            node_type="working_note",
            memory_type=MemoryType.WORKING,
            content="Scratch note from last week's planning session.",
            retention_until=utcnow() - timedelta(days=1),
        )
    )
    active_note = await context_os.ingest(
        ContextNode(
            tenant_id="demo",
            node_type="working_note",
            memory_type=MemoryType.WORKING,
            content="Scratch note still within its retention window.",
            retention_until=utcnow() + timedelta(days=30),
        )
    )
    legal_record = await context_os.ingest(
        ContextNode(
            tenant_id="demo",
            node_type="incident_record",
            memory_type=MemoryType.OPERATIONAL,
            content="Security incident report -- under active legal review.",
            retention_until=utcnow() - timedelta(days=1),  # expired...
            legal_hold=True,  # ...but held, so retention can't touch it.
        )
    )

    print("Trying to delete the legal-hold record directly:")
    try:
        await context_os.delete("demo", legal_record.id)
    except LegalHoldError as exc:
        print(f"  Blocked: {exc}")

    deleted = await context_os.apply_retention_policy("demo")
    print(f"\napply_retention_policy() deleted {len(deleted)} node(s):")
    for node in deleted:
        print(f"  - {node.node_type}: {node.content}")

    print("\nWhat's left in the store:")
    for node_id, label in [
        (expired_note.id, "expired_note"),
        (active_note.id, "active_note"),
        (legal_record.id, "legal_record"),
    ]:
        remaining = await context_os.store.get_node("demo", node_id)
        print(f"  {label}: {'still present' if remaining else 'deleted'}")


if __name__ == "__main__":
    asyncio.run(main())
