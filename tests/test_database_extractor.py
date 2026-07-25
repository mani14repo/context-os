import os
import uuid

import pytest

pytest.importorskip("asyncpg")

from contextos.ingestion.database import DatabaseExtractor

_DSN = os.environ.get("CONTEXTOS_TEST_POSTGRES_DSN")

pytestmark = pytest.mark.skipif(
    not _DSN, reason="CONTEXTOS_TEST_POSTGRES_DSN not set -- skipping live Postgres tests"
)


@pytest.fixture
async def ticket_table() -> str:
    import asyncpg

    table = f"tickets_{uuid.uuid4().hex[:8]}"
    conn = await asyncpg.connect(_DSN)
    try:
        await conn.execute(
            f"CREATE TABLE {table} (id serial PRIMARY KEY, title text, content text, priority text)"
        )
        await conn.execute(
            f"INSERT INTO {table} (title, content, priority) VALUES "
            "('Printer offline', 'The 3rd floor printer is jammed.', 'low'), "
            "('VPN drops', 'VPN disconnects roughly every hour.', 'high')"
        )
        yield table
    finally:
        await conn.execute(f"DROP TABLE IF EXISTS {table}")
        await conn.close()


@pytest.mark.asyncio
async def test_extracts_rows_from_a_real_postgres_table(ticket_table: str) -> None:
    extractor = DatabaseExtractor(_DSN, f"SELECT * FROM {ticket_table} ORDER BY id", id_field="id")

    nodes = await extractor.extract(tenant_id="t1")

    assert len(nodes) == 2
    assert nodes[0].title == "Printer offline"
    assert nodes[0].content == "The 3rd floor printer is jammed."
    assert nodes[0].metadata["source_id"] == 1
    assert nodes[0].metadata["source_type"] == "database"


@pytest.mark.asyncio
async def test_query_args_are_passed_through(ticket_table: str) -> None:
    extractor = DatabaseExtractor(
        _DSN, f"SELECT * FROM {ticket_table} WHERE priority = $1", query_args=["high"]
    )

    nodes = await extractor.extract(tenant_id="t1")

    assert len(nodes) == 1
    assert nodes[0].title == "VPN drops"


@pytest.mark.asyncio
async def test_empty_result_set_yields_no_nodes(ticket_table: str) -> None:
    extractor = DatabaseExtractor(
        _DSN, f"SELECT * FROM {ticket_table} WHERE priority = $1", query_args=["nonexistent"]
    )

    nodes = await extractor.extract(tenant_id="t1")

    assert nodes == []


@pytest.mark.asyncio
async def test_missing_content_field_falls_back_to_json_dump(ticket_table: str) -> None:
    extractor = DatabaseExtractor(
        _DSN, f"SELECT * FROM {ticket_table} ORDER BY id LIMIT 1", content_field="does_not_exist"
    )

    nodes = await extractor.extract(tenant_id="t1")

    assert len(nodes) == 1
    assert "Printer offline" in (nodes[0].content or "")


@pytest.mark.asyncio
async def test_ingest_source_persists_database_rows(ticket_table: str) -> None:
    from contextos import ContextOS

    context_os = ContextOS()
    extractor = DatabaseExtractor(_DSN, f"SELECT * FROM {ticket_table} ORDER BY id")
    nodes = await context_os.ingest_source(extractor, tenant_id="t1")

    assert len(nodes) == 2
    for node in nodes:
        stored = await context_os.store.get_node("t1", node.id)
        assert stored is not None
