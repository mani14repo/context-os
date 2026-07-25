import json
import os
import uuid

import pytest

pytest.importorskip("aiokafka")

from aiokafka import AIOKafkaProducer

from contextos.ingestion.kafka_stream import KafkaEventExtractor

_BOOTSTRAP = os.environ.get("CONTEXTOS_TEST_KAFKA_BOOTSTRAP")

pytestmark = pytest.mark.skipif(
    not _BOOTSTRAP, reason="CONTEXTOS_TEST_KAFKA_BOOTSTRAP not set -- skipping live Kafka tests"
)


async def _produce(topic: str, messages: list[bytes]) -> None:
    producer = AIOKafkaProducer(bootstrap_servers=_BOOTSTRAP)
    await producer.start()
    try:
        for message in messages:
            await producer.send_and_wait(topic, message)
    finally:
        await producer.stop()


def _topic() -> str:
    return f"contextos-test-{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_extracts_plain_text_messages_from_a_real_broker() -> None:
    topic = _topic()
    await _produce(topic, [b"first real message", b"second real message"])

    extractor = KafkaEventExtractor(
        topic, bootstrap_servers=_BOOTSTRAP, group_id=f"g-{uuid.uuid4().hex[:8]}", max_messages=10
    )
    nodes = await extractor.extract(tenant_id="t1")

    assert len(nodes) == 2
    contents = {node.content for node in nodes}
    assert contents == {"first real message", "second real message"}
    assert all(node.metadata["source_type"] == "event_stream" for node in nodes)
    assert all(node.metadata["topic"] == topic for node in nodes)


@pytest.mark.asyncio
async def test_extracts_json_messages_via_content_field() -> None:
    topic = _topic()
    payloads = [
        json.dumps({"id": 1, "title": "Order placed", "content": "Order #1001 was placed."}).encode(),
        json.dumps({"id": 2, "title": "Order shipped", "content": "Order #1001 has shipped."}).encode(),
    ]
    await _produce(topic, payloads)

    extractor = KafkaEventExtractor(
        topic,
        bootstrap_servers=_BOOTSTRAP,
        group_id=f"g-{uuid.uuid4().hex[:8]}",
        content_field="content",
        title_field="title",
        id_field="id",
        max_messages=10,
    )
    nodes = await extractor.extract(tenant_id="t1")

    assert len(nodes) == 2
    titles = {node.title for node in nodes}
    assert titles == {"Order placed", "Order shipped"}
    assert {node.metadata["source_id"] for node in nodes} == {1, 2}


@pytest.mark.asyncio
async def test_max_messages_caps_results() -> None:
    topic = _topic()
    await _produce(topic, [f"message {i}".encode() for i in range(5)])

    extractor = KafkaEventExtractor(
        topic, bootstrap_servers=_BOOTSTRAP, group_id=f"g-{uuid.uuid4().hex[:8]}", max_messages=2
    )
    nodes = await extractor.extract(tenant_id="t1")

    assert len(nodes) <= 2


@pytest.mark.asyncio
async def test_empty_topic_times_out_and_returns_no_nodes() -> None:
    topic = _topic()  # never produced to

    extractor = KafkaEventExtractor(
        topic,
        bootstrap_servers=_BOOTSTRAP,
        group_id=f"g-{uuid.uuid4().hex[:8]}",
        timeout_seconds=1.0,
    )
    nodes = await extractor.extract(tenant_id="t1")

    assert nodes == []


@pytest.mark.asyncio
async def test_ingest_source_persists_kafka_messages() -> None:
    from contextos import ContextOS

    topic = _topic()
    await _produce(topic, [b"a message worth remembering"])

    context_os = ContextOS()
    extractor = KafkaEventExtractor(
        topic, bootstrap_servers=_BOOTSTRAP, group_id=f"g-{uuid.uuid4().hex[:8]}"
    )
    nodes = await context_os.ingest_source(extractor, tenant_id="t1")

    assert len(nodes) == 1
    stored = await context_os.store.get_node("t1", nodes[0].id)
    assert stored is not None
    assert stored.content == "a message worth remembering"
