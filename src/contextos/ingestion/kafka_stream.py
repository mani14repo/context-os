from __future__ import annotations

import json
from typing import Any

from aiokafka import AIOKafkaConsumer
from aiokafka.structs import ConsumerRecord

from contextos.ingestion._mapping import record_to_node
from contextos.models import Classification, ContextNode, MemoryType

__all__ = ["KafkaEventExtractor"]


class KafkaEventExtractor:
    """Consumes messages from a Kafka topic and maps each one to a ContextNode.

    This is a bounded pull, not a running consumer daemon: extract() reads up to
    `max_messages` messages or until `timeout_seconds` elapses, whichever comes
    first, then stops and returns what it has. For continuous ingestion, call
    extract() repeatedly (e.g. from a scheduler) rather than expecting it to block
    forever. If `content_field` is set, each message value is parsed as JSON and
    mapped like APIExtractor/DatabaseExtractor; otherwise the raw decoded message
    text becomes the node's content. Requires `pip install -e ".[kafka]"`.
    """

    def __init__(
        self,
        topic: str,
        *,
        bootstrap_servers: str = "localhost:9092",
        group_id: str = "contextos-ingestion",
        from_beginning: bool = True,
        max_messages: int = 100,
        timeout_seconds: float = 5.0,
        content_field: str | None = None,
        title_field: str | None = None,
        id_field: str | None = None,
        node_type: str = "event",
        memory_type: MemoryType = MemoryType.EPISODIC,
        classification: Classification = Classification.INTERNAL,
        importance: float = 0.5,
    ) -> None:
        self._topic = topic
        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._from_beginning = from_beginning
        self._max_messages = max_messages
        self._timeout_seconds = timeout_seconds
        self._content_field = content_field
        self._title_field = title_field
        self._id_field = id_field
        self._node_type = node_type
        self._memory_type = memory_type
        self._classification = classification
        self._importance = importance

    def _to_node(self, tenant_id: str, message: ConsumerRecord[bytes, bytes]) -> ContextNode:
        raw = message.value.decode("utf-8", errors="replace") if message.value else ""
        extra_metadata: dict[str, Any] = {
            "topic": message.topic,
            "partition": message.partition,
            "offset": message.offset,
        }
        if self._content_field:
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                record = None
            if isinstance(record, dict):
                return record_to_node(
                    tenant_id,
                    record,
                    content_field=self._content_field,
                    title_field=self._title_field,
                    id_field=self._id_field,
                    node_type=self._node_type,
                    memory_type=self._memory_type,
                    classification=self._classification,
                    importance=self._importance,
                    source_type="event_stream",
                    extra_metadata=extra_metadata,
                )
        return ContextNode(
            tenant_id=tenant_id,
            node_type=self._node_type,
            memory_type=self._memory_type,
            classification=self._classification,
            content=raw,
            importance=self._importance,
            metadata={"source_type": "event_stream", **extra_metadata},
        )

    async def extract(self, *, tenant_id: str) -> list[ContextNode]:
        consumer: AIOKafkaConsumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            auto_offset_reset="earliest" if self._from_beginning else "latest",
            enable_auto_commit=True,
        )
        await consumer.start()
        try:
            batches = await consumer.getmany(
                timeout_ms=int(self._timeout_seconds * 1000), max_records=self._max_messages
            )
            messages = [message for partition_messages in batches.values() for message in partition_messages]
        finally:
            await consumer.stop()
        return [self._to_node(tenant_id, message) for message in messages]
