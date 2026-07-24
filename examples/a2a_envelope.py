"""Exchange context with another agent over A2A (Agent2Agent protocol).

Requires: pip install -e ".[a2a]"

Two directions, both using the official `a2a-sdk` protobuf types directly (not a
hand-rolled approximation of the wire format):

1. Outbound: `context_package_to_artifact()` turns an assembled ContextPackage into
   a real `a2a.types.Artifact`, ready to attach to a Task/Message response for
   another A2A agent.
2. Inbound: `a2a_message_to_context_node()` turns an `a2a.types.Message` received
   from another agent into a ContextNode, ready for `ContextOS.ingest()` -- so what
   another agent tells us becomes part of this agent's own memory instead of being
   lost once the turn ends.
"""

import asyncio

from a2a.types import Message, Part, Role
from google.protobuf.json_format import MessageToDict

from contextos import ContextNode, ContextOS, ContextRequest, MemoryType
from contextos.integrations.a2a import a2a_message_to_context_node, context_package_to_artifact


async def main() -> None:
    context_os = ContextOS()
    await context_os.ingest(
        ContextNode(
            tenant_id="demo",
            node_type="project_convention",
            memory_type=MemoryType.SEMANTIC,
            title="Release convention",
            content="Stable releases use semantic versioning and include a changelog.",
            importance=0.9,
        )
    )

    # --- Outbound: share assembled context with another A2A agent ---
    package = await context_os.assemble(
        ContextRequest(
            tenant_id="demo",
            task="What is required for a stable release?",
            agent="release-assistant",
            token_budget=500,
        )
    )
    artifact = context_package_to_artifact(package, artifact_id="release-context-1")
    print("Outbound A2A Artifact (real wire format via MessageToDict):")
    print(MessageToDict(artifact))

    # --- Inbound: another agent tells us something; remember it ---
    incoming = Message(
        message_id="msg-1",
        context_id="ctx-1",
        role=Role.ROLE_AGENT,
        parts=[Part(text="The previous DR test failed because Keycloak restoration was incomplete.")],
    )
    node = a2a_message_to_context_node(incoming, tenant_id="demo")
    stored = await context_os.ingest(node)
    print(f"\nInbound A2A Message stored as ContextNode {stored.id}")
    print(f"  content: {stored.content!r}")
    print(f"  metadata: {stored.metadata}")


if __name__ == "__main__":
    asyncio.run(main())
