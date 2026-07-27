"""Content-safety moderation with a policy-specific KeywordModerator.

No optional extras needed.

`ContextOS.moderate()` has no automatic trigger and no dependency-free default
(unlike `redact()`) -- there's no sensible built-in moderation heuristic the way
`RegexRedactor`'s PII patterns are, so a `Moderator` must be configured explicitly.
This example uses `contextos.moderation.KeywordModerator`, well-suited to
fixed-vocabulary policy enforcement (an unannounced product codename that
shouldn't leak into public-facing content) rather than general-purpose toxicity
detection, which needs a real classifier or moderation API implementing the same
`Moderator` protocol.

Shows both directions: pre-flight screening before `ingest()` (flagging
policy-sensitive notes with a stricter classification, not necessarily blocking
them -- they may be legitimate internal knowledge), and post-flight screening of
each *individually retrieved* item before deciding what's safe to return to an
external-facing channel, rather than only checking the aggregated output.
"""

import asyncio

from contextos import Classification, ContextNode, ContextOS, ContextRequest, MemoryType
from contextos.moderation import KeywordModerator


async def main() -> None:
    context_os = ContextOS(moderator=KeywordModerator(["Project Phoenix"]))

    # --- Pre-flight: screen content before ingest() ---
    notes = [
        "Engineering update: the beta rollout ships to customers next Tuesday.",
        "Engineering update: Project Phoenix ships to beta customers next Tuesday.",
    ]
    for text in notes:
        report = await context_os.moderate(text)
        print(f"Pre-flight: flagged={report.flagged} categories={report.categories}")
        print(f"  \"{text}\"")
        await context_os.ingest(
            ContextNode(
                tenant_id="demo",
                node_type="note",
                memory_type=MemoryType.WORKING,
                content=text,
                classification=Classification.CONFIDENTIAL if report.flagged else Classification.INTERNAL,
            )
        )

    # --- Post-flight: screen each retrieved item before returning externally ---
    # Both notes are legitimately in the store (internal knowledge), but only one
    # of them is safe to hand to, say, a public-facing support bot.
    package = await context_os.assemble(
        ContextRequest(tenant_id="demo", task="engineering update", agent="support-bot", token_budget=500)
    )
    print(f"\nassemble() retrieved {len(package.items)} item(s); checking each before returning any of them:")
    for item in package.items:
        representation = item.node.representations[-1] if item.node.representations else None
        content = representation.content if representation else item.node.content
        report = await context_os.moderate(content or "")
        verdict = "BLOCK before returning externally" if report.flagged else "safe to return"
        print(f"  [{verdict}] \"{content}\"")

    print(f"\nThis assemble() call also saved {package.tokens_saved} token(s) via compaction.")


if __name__ == "__main__":
    asyncio.run(main())
