from __future__ import annotations

from a2a.types import Artifact, Message, Part, Role
from google.protobuf.struct_pb2 import Struct

from contextos.models import ContextNode, ContextPackage, MemoryType

__all__ = ["a2a_message_to_context_node", "context_package_to_artifact"]


def context_package_to_artifact(
    package: ContextPackage, *, artifact_id: str, name: str = "context"
) -> Artifact:
    """Convert an assembled ContextPackage into an A2A Artifact -- one Part per
    ranked item -- so it can be attached to a Task/Message response for another A2A
    agent. Requires `pip install -e ".[a2a]"`.

    Uses the official `a2a-sdk` protobuf types directly rather than hand-rolled JSON,
    so the result serializes to the real A2A wire format (verify with
    `google.protobuf.json_format.MessageToDict`, as the tests do) instead of an
    approximation of it.
    """
    parts = []
    for item in package.items:
        representation = item.node.representations[-1] if item.node.representations else None
        content = representation.content if representation else (item.node.summary or item.node.title)
        parts.append(Part(text=content or ""))
    metadata = Struct()
    metadata.update(
        {
            "contextos.tenant_id": package.request.tenant_id,
            "contextos.token_count": package.token_count,
            "contextos.item_count": len(package.items),
        }
    )
    return Artifact(artifact_id=artifact_id, name=name, parts=parts, metadata=metadata)


def a2a_message_to_context_node(
    message: Message,
    *,
    tenant_id: str,
    node_type: str = "a2a_message",
    memory_type: MemoryType = MemoryType.EPISODIC,
    importance: float = 0.5,
) -> ContextNode:
    """Convert an inbound A2A Message into a ContextNode, ready for
    `ContextOS.ingest()` -- so context received from another agent over A2A becomes
    part of this agent's own memory instead of being lost once the turn ends. Only
    text parts are captured; A2A file/data parts aren't extracted here (they'd
    typically go through `ContextOS.store_artifact()` instead of inline `content`).
    """
    content = "\n".join(part.text for part in message.parts if part.text)
    return ContextNode(
        tenant_id=tenant_id,
        node_type=node_type,
        memory_type=memory_type,
        content=content,
        importance=importance,
        metadata={
            "a2a_message_id": message.message_id,
            "a2a_context_id": message.context_id or None,
            "a2a_role": Role.Name(message.role) if message.role else None,
        },
    )
