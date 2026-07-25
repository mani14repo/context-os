"""Ingesting real Kafka messages into ContextOS.

Needs `pip install -e ".[kafka]"` and a running Kafka broker (`docker compose up kafka`).

`KafkaEventExtractor` is a bounded pull: it reads up to `max_messages` messages, or
stops after `timeout_seconds` if fewer arrive, then returns. For continuous
ingestion, call it repeatedly (e.g. on a schedule) rather than expecting it to
block forever.
"""

import asyncio
import os
import uuid

from aiokafka import AIOKafkaProducer

from contextos import ContextOS
from contextos.ingestion.kafka_stream import KafkaEventExtractor

BOOTSTRAP = os.environ.get("CONTEXTOS_KAFKA_BOOTSTRAP", "localhost:9092")


async def main() -> None:
    topic = f"contextos-demo-{uuid.uuid4().hex[:8]}"

    producer = AIOKafkaProducer(bootstrap_servers=BOOTSTRAP)
    await producer.start()
    try:
        await producer.send_and_wait(topic, b"Deployment to us-east-1 completed successfully.")
        await producer.send_and_wait(topic, b"Error rate spiked to 4% for 90 seconds post-deploy.")
    finally:
        await producer.stop()

    context_os = ContextOS()
    extractor = KafkaEventExtractor(
        topic, bootstrap_servers=BOOTSTRAP, group_id=f"demo-{uuid.uuid4().hex[:8]}"
    )
    nodes = await context_os.ingest_source(extractor, tenant_id="acme")

    print(f"ingest_source() pulled {len(nodes)} real Kafka message(s):")
    for node in nodes:
        print(f"  [{node.metadata['topic']}@{node.metadata['offset']}] {node.content}")


if __name__ == "__main__":
    asyncio.run(main())
