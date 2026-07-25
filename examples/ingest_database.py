"""Ingesting rows from a real PostgreSQL query into ContextOS.

Needs `pip install -e ".[postgres]"` and a running Postgres (e.g. `docker compose up postgres`).

`DatabaseExtractor` runs a SQL query and maps each result row to a ContextNode via
the same field-mapping approach as APIExtractor -- a query result is, structurally,
just another list of records with named fields.
"""

import asyncio
import os
import uuid

import asyncpg

from contextos import ContextOS
from contextos.ingestion.database import DatabaseExtractor

DSN = os.environ.get("CONTEXTOS_POSTGRES_DSN", "postgresql://postgres:contextos@localhost:5432/contextos")


async def main() -> None:
    table = f"tickets_{uuid.uuid4().hex[:8]}"
    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute(f"CREATE TABLE {table} (id serial PRIMARY KEY, title text, content text)")
        await conn.execute(
            f"INSERT INTO {table} (title, content) VALUES "
            "('Printer offline', 'The 3rd floor printer is jammed and offline.'), "
            "('VPN drops', 'VPN disconnects roughly once an hour for remote staff.')"
        )

        context_os = ContextOS()
        extractor = DatabaseExtractor(DSN, f"SELECT * FROM {table} ORDER BY id", id_field="id")
        nodes = await context_os.ingest_source(extractor, tenant_id="acme")

        print(f"ingest_source() pulled {len(nodes)} row(s) from Postgres:")
        for node in nodes:
            print(f"  #{node.metadata['source_id']} {node.title}: {node.content}")
    finally:
        await conn.execute(f"DROP TABLE IF EXISTS {table}")
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
