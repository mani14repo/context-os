# ContextOS

[![CI](https://github.com/mani14repo/context-os/actions/workflows/ci.yml/badge.svg)](https://github.com/mani14repo/context-os/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

**ContextOS** is an open-source, agent-neutral context operating system for building governed AI memory and context pipelines.

It provides a small set of composable primitives for:

- working, semantic, episodic, operational, procedural, and artifact memory;
- temporal context nodes and typed graph relationships;
- hot, warm, cold, and archive storage tiers;
- progressive context compaction;
- task-specific, token-budgeted context assembly;
- multi-tenant isolation and provenance;
- integration with LangGraph, MCP, A2A, or custom agent runtimes.

> Status: alpha. The included in-memory implementation is usable for prototypes and tests. Production storage adapters are intentionally separate extension points.

## Why ContextOS?

Agent frameworks execute workflows. Vector databases retrieve similar chunks. Knowledge graphs represent relationships. Memory products retain prior interactions. ContextOS defines the control plane that combines these ideas into a governed context lifecycle.

```text
Sources → Ingestion → Context Graph → Context Orchestrator
                                      ├─ Memory scopes
                                      ├─ Compaction levels
                                      ├─ Storage tiers
                                      └─ Token budgets
                                               ↓
                                  Dynamic Context Package
                                               ↓
                                      Agent Runtime
```

## Install

```bash
pip install -e .
```

For the API:

```bash
pip install -e ".[api]"
contextos-api
```

Open `http://localhost:8080/docs` for the API explorer.

For the persisted PostgreSQL + pgvector store:

```bash
pip install -e ".[postgres]"
docker compose up postgres   # or any Postgres with the pgvector extension
```

For the Redis working-memory/cache layer:

```bash
pip install -e ".[redis]"
docker compose up redis
```

For artifact storage (large/original content behind a `content_pointer`):

```bash
pip install -e ".[s3]"          # Amazon S3 or any S3-compatible service (MinIO, ...)
pip install -e ".[azure-blob]"  # Azure Blob Storage (or the Azurite emulator)
docker compose up minio azurite
```

For OpenTelemetry tracing:

```bash
pip install -e ".[otel]"
```

## Five-minute example

```python
import asyncio
from contextos import ContextNode, ContextOS, ContextRequest, MemoryType

async def main():
    os = ContextOS()
    await os.ingest(ContextNode(
        tenant_id="acme",
        node_type="project_note",
        memory_type=MemoryType.SEMANTIC,
        title="Release convention",
        content="Stable releases use semantic versioning and require a changelog.",
        importance=0.9,
        source_authority=0.9,
    ))

    package = await os.assemble(ContextRequest(
        tenant_id="acme",
        task="What is required before publishing a stable release?",
        agent="release-assistant",
        memory_scopes={MemoryType.SEMANTIC},
        token_budget=500,
    ))
    print(package.model_dump_json(indent=2))

asyncio.run(main())
```

## Examples

| Script | Demonstrates |
|---|---|
| `examples/basic.py` | Ingest, link, and assemble against the in-memory reference store |
| `examples/langgraph_integration.py` | Wiring `ContextOS.assemble()`/`ingest()` into a LangGraph `StateGraph` (needs `pip install -e ".[langgraph]"`) |
| `examples/sqlite_persistent_store.py` | Context surviving across process restarts with `SQLiteContextStore` |
| `examples/replaceable_infrastructure.py` | Running identical code against the in-memory store, the SQLite store, and a custom `Compactor` |
| `examples/progressive_retrieval.py` | The six-level compaction ladder, and `assemble()` automatically downgrading representations to fit a token budget |
| `examples/postgres_pgvector_store.py` | Real vector similarity search via pgvector's cosine-distance operator, ranked by an `EmbeddingProvider` instead of lexical overlap (needs `pip install -e ".[postgres]"` and a running Postgres) |
| `examples/redis_cache.py` | Wrapping any store with a Redis TTL cache for `get_node()`, with call counts showing cache hits vs. misses and invalidation on write (needs `pip install -e ".[redis]"` and a running Redis) |
| `examples/s3_artifact_store.py` | Storing a node's original content in S3/MinIO and loading it back via `content_pointer` (needs `pip install -e ".[s3]"` and a running S3-compatible service) |
| `examples/azure_blob_store.py` | Same, backed by Azure Blob Storage/Azurite (needs `pip install -e ".[azure-blob]"`) |
| `examples/opentelemetry_tracing.py` | Real spans for `ingest()`/`assemble()`/`move()` printed to the console via the OpenTelemetry SDK (needs `pip install -e ".[otel]"`) |

## Core concepts

### Context node

A versioned unit of context with a memory class, confidence, importance, authority, temporal validity, storage tier, content pointers, and compacted representations.

### Context edge

A tenant-scoped relationship such as `supports`, `contradicts`, `supersedes`, `derived_from`, `depends_on`, `includes`, or a domain-defined relationship.

### Context orchestrator

Searches relevant memory scopes, expands graph neighbors, ranks candidates, chooses compact representations, and produces a context package within a token budget.

### Progressive representations

Each node can retain metadata, one-line, compact, detailed, full, and original representations. Compaction never destroys provenance or the original source pointer.

## Repository layout

```text
src/contextos/
├── models.py                # Stable domain contracts
├── protocols.py             # Storage and graph extension points
├── library.py               # High-level facade
├── storage/memory.py        # In-memory reference implementation
├── storage/sqlite.py        # Stdlib-only persisted implementation
├── storage/postgres.py      # PostgreSQL + pgvector persisted implementation
├── storage/redis_cache.py   # Redis TTL cache wrapping any FullContextStore
├── storage/s3_artifacts.py  # ArtifactStore backed by S3 or S3-compatible services
├── storage/azure_artifacts.py # ArtifactStore backed by Azure Blob Storage
├── embeddings.py            # Dependency-free reference EmbeddingProvider
├── tracing.py                # No-op-safe OpenTelemetry span helper
├── compaction/simple.py     # Deterministic fallback compactor
├── orchestration/           # Retrieval, ranking, budget fitting
├── api/app.py               # Optional FastAPI service
└── integrations/langgraph.py # LangGraph prompt-formatting helper
```

## Extending ContextOS

`ContextOS` accepts five independently swappable collaborators, each defined as a
`Protocol` in `contextos.protocols` so a custom implementation only needs to match
the method signatures — no base class to inherit:

```python
from contextos import ContextOS

os = ContextOS(
    store=MyPostgresStore(),      # implements contextos.protocols.ContextStore
    graph=MyGraphBackend(),       # implements contextos.protocols.GraphStore, defaults to `store`
    compactor=MyLLMCompactor(),   # implements contextos.protocols.Compactor, defaults to SimpleCompactor
    tier_manager=MyTierManager(), # implements contextos.protocols.TierManager, defaults to `store`
    access_log=MyAccessLog(),     # implements contextos.protocols.AccessLog, defaults to `store`
)
```

If you only override `store`, the other four fall back to it automatically, matching
the built-in `InMemoryContextStore` and `SQLiteContextStore`, which each implement all
five protocols at once. See `CONTRIBUTING.md` for the expectation that new storage or
model providers implement these protocols rather than coupling the core package to a
specific vendor.

`PostgresContextStore` (`contextos.storage.postgres`, needs `pip install -e ".[postgres]"`)
adds a sixth extension point, `EmbeddingProvider` (`contextos.protocols.EmbeddingProvider`):

```python
from contextos.storage.postgres import PostgresContextStore

store = await PostgresContextStore.connect(
    "postgresql://localhost/contextos",
    embeddings=MyRealEmbeddingProvider(),  # implements EmbeddingProvider.embed(text) -> vector
    dimensions=1536,                        # must match the provider's output size
)
```

`contextos.embeddings.HashingEmbeddingProvider` is the dependency-free default (used in
`examples/postgres_pgvector_store.py`) — see its docstring for exactly what it does and
does not capture.

`RedisCachedContextStore` (`contextos.storage.redis_cache`, needs `pip install -e ".[redis]"`)
is a decorator, not a standalone backend: it wraps any store that implements all four
storage protocols at once (`contextos.protocols.FullContextStore` — every built-in
store does) and adds a Redis TTL cache in front of `get_node()`, invalidated on
write/move/delete. This is the "working-memory/cache adapter" from the roadmap:

```python
import redis.asyncio as redis
from contextos.storage.postgres import PostgresContextStore
from contextos.storage.redis_cache import RedisCachedContextStore

primary = await PostgresContextStore.connect(dsn, embeddings, dimensions=1536)
store = RedisCachedContextStore(primary, redis.from_url("redis://localhost:6379/0"))
os = ContextOS(store=store)  # graph/tier_manager/access_log still default to `store`
```

`ContextOS(artifacts=...)` accepts a seventh, independent collaborator implementing
`contextos.protocols.ArtifactStore` (`S3ArtifactStore`, needs `pip install -e ".[s3]"`;
`AzureBlobArtifactStore`, needs `pip install -e ".[azure-blob]"`) for the "graph-content
separation" principle: `ContextOS.store_artifact()`/`load_artifact()` write/read large
original content and give you back a pointer for `ContextNode.content_pointer`. Unlike
the other five collaborators, there's no in-process fallback — it stays `None` unless
you configure one, since `InMemoryContextStore`/`SQLiteContextStore` don't implement it.

## Observability

`contextos.tracing.start_span()` wraps `ingest()`, `link()`, `compact()`, `move()`,
`apply_tiering_policy()`, and `assemble()`. It's called unconditionally from core code
but does nothing unless you `pip install -e ".[otel]"` and configure an OpenTelemetry
SDK/exporter — see `examples/opentelemetry_tracing.py` for a runnable demo with spans
printed to the console, including the `contextos.item_count`/`contextos.token_count`
attributes `assemble()` records.

## Versioning, temporal validity, access logging, and tiering

A few of the design principles from the architecture-decisions section are enforced,
not just modeled:

- **Immutable history.** `ContextStore.put_node()` archives the prior version instead
  of overwriting it whenever you re-ingest an existing node id, and bumps `version`.
  Retrieve prior versions with `ContextOS.history(tenant_id, node_id)`.
- **Temporal validity.** `valid_from`/`valid_to` are enforced during `search()` (via
  `ContextQuery.as_of`, defaulting to now) and during graph traversal — expired nodes
  and edges are excluded automatically.
- **Access logging.** Every node included in an assembled `ContextPackage` is recorded
  via the `AccessLog` protocol (`record`/`last_accessed`), keyed by tenant, agent, and
  task.
- **Automatic tiering.** `ContextOS.apply_tiering_policy(tenant_id)` re-tiers nodes
  using `contextos.tiering.suggest_tier()` — active-workflow nodes go hot, recently
  accessed or high-importance nodes go warm, nodes flagged `retention_required` go
  cold, everything else drifts to archive. It's invoked explicitly (there's no
  background scheduler in a library), but the decision itself is policy-driven rather
  than manual.

## Known limitations

Known gaps, tracked as GitHub issues:

- No ingestion pipeline: `ContextOS.ingest()` stores the `ContextNode` you hand it as-is —
  there is no automatic classification or entity extraction.
- `InMemoryContextStore`/`SQLiteContextStore` rank by lexical token overlap, not
  embeddings. `PostgresContextStore` ranks by real pgvector cosine distance, but its
  default `HashingEmbeddingProvider` captures shared vocabulary, not meaning — plug in
  a real embedding model via the same protocol for genuine semantic search.
- No governance layer (authorization, retention rules, redaction) — see `SECURITY.md`.
- No contradiction/supersession resolution: edges can be tagged `contradicts` or
  `supersedes`, but nothing acts on that yet.
- `apply_tiering_policy()` processes at most 200 nodes per tenant per call (the
  `ContextQuery.max_results` ceiling); there's no pagination for larger tenants yet.
- `PostgresContextStore`'s vector `dimensions` is fixed at table-creation time; changing
  embedding providers/dimensions after data exists needs an explicit migration.
- `S3ArtifactStore`/`AzureBlobArtifactStore` namespace pointers by tenant_id in the key
  path (`bucket/tenant_id/key`), but nothing enforces that a caller can't construct a
  pointer for another tenant's key directly — access control at that boundary is an
  application concern, same as the reference ContextStores (see `SECURITY.md`).

## Roadmap

### 0.1 — Foundation

- [x] Memory taxonomy
- [x] Temporal nodes and edges, with validity enforced in search and traversal
- [x] Multi-tenant in-memory store
- [x] Progressive compaction contract
- [x] Token-budgeted context assembly
- [x] FastAPI and Docker entry points
- [x] Tests and GitHub Actions
- [x] Immutable node history/versioning on update
- [x] Access logging and a policy-driven (if manually invoked) tiering function

### 0.2 — Production adapters

- [x] SQLite persisted store (stdlib-only, see `examples/sqlite_persistent_store.py`)
- [x] PostgreSQL + pgvector store, with real vector similarity search
- [x] Pluggable embedding providers (`EmbeddingProvider` protocol + dependency-free
      reference implementation; reranking providers still open)
- [x] Redis working-memory/cache adapter (`RedisCachedContextStore` — a TTL cache
      decorator over any store, not a standalone backend; see `examples/redis_cache.py`)
- [x] S3/Azure Blob artifact adapter (`S3ArtifactStore`/`AzureBlobArtifactStore`,
      `ArtifactStore` protocol; validated against MinIO and Azurite)
- [x] OpenTelemetry traces (`contextos.tracing.start_span()`; no-op unless the SDK is
      configured, wraps ingest/link/compact/move/apply_tiering_policy/assemble)

### 0.3 — Governance

- [ ] Authorization decision point and ABAC hooks
- [ ] Retention rules and legal-hold support
- [ ] Context redaction and classification
- [ ] Contradiction and supersession workflows
- [ ] Immutable provenance manifests

### 0.4 — Agent ecosystem

- [x] LangGraph example (`examples/langgraph_integration.py`) — a full checkpointer/store adapter is still open
- [ ] LangGraph state and store adapter
- [ ] MCP context server
- [ ] A2A context exchange envelope
- [ ] Framework-neutral evaluation suite

## Architecture decisions

1. **Agent-neutral core:** no mandatory LangChain or LangGraph dependency.
2. **Logical memory types:** memory classes do not require separate databases.
3. **Graph-content separation:** large artifacts remain in object stores; nodes carry pointers.
4. **Immutable history:** updates create versions; compact summaries supplement originals.
5. **Progressive retrieval:** hot/warm summaries first, cold/archive detail only when required.
6. **Replaceable infrastructure:** protocols allow PostgreSQL, Neo4j, Redis, or cloud adapters.

## Security

The reference store is not a production security boundary. Production deployments must enforce authentication, tenant authorization, content-level access control, encryption, auditing, retention, and prompt-injection defenses. See `SECURITY.md`.

## License

Apache License 2.0.
