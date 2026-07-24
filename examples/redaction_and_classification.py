"""Classification labels and content redaction.

No optional extras needed.

`ContextNode.classification` (public/internal/confidential/restricted) is a label,
not an enforcement mechanism -- ContextOS has no authorization concept (see README
"Known limitations"), so it doesn't decide who's allowed to see what. What it does
provide is `ContextOS.redact()`, a data transformation a caller can apply explicitly
before handing confidential content to an untrusted destination (a third-party LLM
call, a public-facing summary, a support ticket). The default `RegexRedactor` strips
common PII patterns; swap in an NER/LLM-backed `Redactor` for anything beyond that.
"""

import asyncio

from contextos import Classification, ContextNode, ContextOS, MemoryType


async def main() -> None:
    context_os = ContextOS()

    incident = await context_os.ingest(
        ContextNode(
            tenant_id="demo",
            node_type="incident_note",
            memory_type=MemoryType.OPERATIONAL,
            classification=Classification.CONFIDENTIAL,
            content=(
                "Customer jane.doe@example.com reported the outage at 555-123-4567. "
                "Her account SSN on file is 123-45-6789 for verification."
            ),
        )
    )
    print(f"Node classification: {incident.classification.value}")
    print(f"Original content:\n  {incident.content}")

    redacted = await context_os.redact(incident.content or "")
    print(f"\nRedacted content (safe to forward to a third-party support ticket):\n  {redacted}")

    # Classification is just a label -- nothing stops you from reading the original
    # unless *you* choose to gate on it. A minimal, honest policy a caller could apply:
    if incident.classification in (Classification.CONFIDENTIAL, Classification.RESTRICTED):
        outbound_content = redacted
    else:
        outbound_content = incident.content
    print(f"\nWhat an outbound integration should actually send:\n  {outbound_content}")


if __name__ == "__main__":
    asyncio.run(main())
