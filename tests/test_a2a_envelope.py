import pytest

pytest.importorskip("a2a")

from a2a.types import Message, Part, Role
from google.protobuf.json_format import MessageToDict

from contextos import ContextNode, ContextOS, ContextRequest, MemoryType
from contextos.integrations.a2a import (
    a2a_message_to_context_node,
    context_package_to_artifact,
)


@pytest.mark.asyncio
async def test_context_package_to_artifact_wire_format() -> None:
    context_os = ContextOS()
    await context_os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            title="Release convention",
            content="Stable releases use semantic versioning and include a changelog.",
            importance=0.9,
        )
    )
    package = await context_os.assemble(
        ContextRequest(
            tenant_id="t1",
            task="What is required for a stable release?",
            agent="release-assistant",
            token_budget=500,
        )
    )
    artifact = context_package_to_artifact(package, artifact_id="art-1", name="release-context")

    wire = MessageToDict(artifact)
    assert wire["artifactId"] == "art-1"
    assert wire["name"] == "release-context"
    assert len(wire["parts"]) == 1
    assert "semantic versioning" in wire["parts"][0]["text"]
    assert wire["metadata"]["contextos.tenant_id"] == "t1"
    assert wire["metadata"]["contextos.item_count"] == 1.0


@pytest.mark.asyncio
async def test_context_package_to_artifact_empty_package() -> None:
    context_os = ContextOS()
    package = await context_os.assemble(
        ContextRequest(tenant_id="t1", task="anything", agent="a", token_budget=500)
    )
    artifact = context_package_to_artifact(package, artifact_id="art-empty")
    assert MessageToDict(artifact).get("parts", []) == []


def test_a2a_message_to_context_node_captures_text_and_metadata() -> None:
    message = Message(
        message_id="msg-1",
        context_id="ctx-1",
        role=Role.ROLE_AGENT,
        parts=[Part(text="The DR test failed because Keycloak restoration was incomplete.")],
    )
    node = a2a_message_to_context_node(message, tenant_id="t1")

    assert node.tenant_id == "t1"
    assert node.node_type == "a2a_message"
    assert node.memory_type == MemoryType.EPISODIC
    assert node.content == "The DR test failed because Keycloak restoration was incomplete."
    assert node.metadata == {
        "a2a_message_id": "msg-1",
        "a2a_context_id": "ctx-1",
        "a2a_role": "ROLE_AGENT",
    }


def test_a2a_message_to_context_node_joins_multiple_text_parts() -> None:
    message = Message(
        message_id="msg-2",
        role=Role.ROLE_USER,
        parts=[Part(text="First fact."), Part(text="Second fact.")],
    )
    node = a2a_message_to_context_node(message, tenant_id="t1")
    assert node.content == "First fact.\nSecond fact."


@pytest.mark.asyncio
async def test_converted_node_is_ingestible() -> None:
    message = Message(
        message_id="msg-3",
        role=Role.ROLE_AGENT,
        parts=[Part(text="Kubernetes cluster upgrades require draining nodes first.")],
    )
    node = a2a_message_to_context_node(message, tenant_id="t1")
    context_os = ContextOS()
    stored = await context_os.ingest(node)
    reloaded = await context_os.store.get_node("t1", stored.id)
    assert reloaded is not None
    assert reloaded.content == node.content
