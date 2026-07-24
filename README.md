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

For the MCP context server:

```bash
pip install -e ".[mcp]"
contextos-mcp
```

For the LangGraph `BaseStore` adapter (cross-thread memory) and the A2A context
exchange envelope:

```bash
pip install -e ".[langgraph]"
pip install -e ".[a2a]"
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
| `examples/mcp_server.py` | Calling `ingest_context`/`assemble_context` over a real MCP `ClientSession` round trip, not a direct Python call (needs `pip install -e ".[mcp]"`) |
| `examples/langgraph_store.py` | `ContextOSStore` as a LangGraph `BaseStore`, plugged into `StateGraph.compile(store=...)` for cross-thread memory that persists through ContextOS (needs `pip install -e ".[langgraph]"`) |
| `examples/a2a_envelope.py` | Converting a `ContextPackage` to a real `a2a.types.Artifact` and an inbound `a2a.types.Message` to a `ContextNode`, using the official `a2a-sdk` types (needs `pip install -e ".[a2a]"`) |
| `examples/evaluation_suite.py` | Scoring `assemble()`'s retrieval precision/recall/f1 against known-correct node ids -- and showing a real precision gap the ranking formula has on a small corpus |

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
├── evaluation.py             # Framework-neutral precision/recall/f1 eval suite
├── api/app.py               # Optional FastAPI service
├── integrations/langgraph.py # LangGraph prompt-formatting helper + BaseStore adapter
├── integrations/mcp_server.py # MCP tool server wrapping a ContextOS instance
└── integrations/a2a.py       # A2A Artifact/Message <-> ContextPackage/ContextNode envelope
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

`Compactor` is intentionally a single, stateless call — `compact(node, level)` in, one
`ContextRepresentation` out, no memory of prior calls. A custom `Compactor` can run
something more elaborate internally (an LLM call, a generate/reflect/curate loop like
[ACE-style "context playbook" agents](https://arxiv.org/abs/2510.04618) use to refine
strategies over iterations) and still satisfy the protocol. What doesn't fit is the
*persistent, delta-updated playbook* those patterns rely on: `compact()` has no state
across calls, so an evolving shared artifact is better modeled as an ordinary
`ContextNode` that a Generator/Reflector/Curator pipeline updates via `ContextOS.ingest()`
(each update versioned automatically — see "Immutable history" below) rather than as a
`Compactor`. Compaction and playbook-curation are related but distinct concerns here.

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

## MCP integration

`contextos.integrations.mcp_server.build_context_server(context_os)` wraps any
`ContextOS` instance as an MCP server (needs `pip install -e ".[mcp]"`), exposing
`ingest_context`, `search_context`, `assemble_context`, `link_context`, `move_context`,
and `context_history` as MCP tools — so any MCP client (Claude Desktop, another agent,
an eval harness) can use ContextOS over the standard protocol instead of only from
Python in the same process. `assemble_context` is the one worth reaching for first;
the others exist so a client can also write and manage context, not just read it.

```bash
contextos-mcp   # runs an in-memory ContextOS over stdio
```

```python
from contextos import ContextOS
from contextos.integrations.mcp_server import build_context_server
from contextos.storage.sqlite import SQLiteContextStore

server = build_context_server(ContextOS(store=SQLiteContextStore("context.db")))
server.run()  # stdio by default; see FastMCP.run() for sse/streamable-http
```

See `examples/mcp_server.py` for a runnable demo that connects a real `ClientSession`
over in-memory streams and calls tools exactly as an external client would.

## LangGraph `BaseStore` adapter

`contextos.integrations.langgraph.ContextOSStore` implements LangGraph's `BaseStore`
interface (needs `pip install -e ".[langgraph]"`), so it plugs directly into
`StateGraph.compile(store=...)` and becomes LangGraph's cross-thread/long-term memory,
persisted through whatever ContextStore ContextOS is configured with instead of
LangGraph's own store implementations:

```python
from contextos import ContextOS
from contextos.integrations.langgraph import ContextOSStore

store = ContextOSStore(ContextOS())
app = graph.compile(store=store)
# inside a node: await langgraph.config.get_store().aput((user_id, "memories"), key, value)
```

`namespace[0]` becomes the ContextOS `tenant_id`; get/put/delete are direct
`ContextStore` calls by a deterministic id derived from the full namespace + key, not
a search. See the class docstring for the `search()`/`list_namespaces()` pagination
caveat and why the sync `batch()` raises `NotImplementedError` (ContextOS is
async-only throughout). `examples/langgraph_store.py` has a full runnable demo.

## A2A context exchange envelope

`contextos.integrations.a2a` (needs `pip install -e ".[a2a]"`) converts between
ContextOS and the official `a2a-sdk` types in both directions:

- `context_package_to_artifact(package, artifact_id=...)` -- an assembled
  `ContextPackage` becomes a real `a2a.types.Artifact` (one `Part` per ranked item),
  ready to attach to a Task/Message response for another A2A agent.
- `a2a_message_to_context_node(message, tenant_id=...)` -- an inbound
  `a2a.types.Message` becomes a `ContextNode` ready for `ContextOS.ingest()`, so
  what another agent tells us becomes part of this agent's own memory.

These use the SDK's protobuf types directly, not a hand-rolled approximation of the
wire format -- `examples/a2a_envelope.py` verifies the real JSON shape via
`google.protobuf.json_format.MessageToDict`.

## Framework-neutral evaluation suite

`contextos.evaluation.run_eval_suite()` needs no optional extras -- it only exercises
`ContextOS.assemble()`, independent of whatever agent runtime calls it. Define
`EvalCase`s (a task plus the node ids that should come back, or an empty set if
nothing should), run the suite, get precision/recall/f1/latency per case plus
aggregate means:

```python
from contextos.evaluation import EvalCase, run_eval_suite

report = await run_eval_suite(context_os, [
    EvalCase(case_id="c1", tenant_id="acme", task="...", expected_node_ids={node.id}),
])
```

`examples/evaluation_suite.py` runs this for real and surfaces an honest finding, not
a staged pass: precision comes out below 1.0 even on an off-topic case, because
`_rank()`'s score always includes an importance term, so a sufficiently important node
can clear the relevance bar for a nearly-unrelated task (see "Known limitations").

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
- `SimpleCompactor` is deterministic sentence-count truncation with no reflection or
  iterative refinement — see the `Compactor` note under "Extending ContextOS" for how a
  more elaborate custom `Compactor` would fit, and why an evolving curated artifact
  (a "context playbook") is a versioned `ContextNode`, not a `Compactor`, in this design.
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
- The MCP context server takes `tenant_id` as a plain tool argument with no
  authentication or per-connection scoping — any client that can call the server can
  act as any tenant. Fine for local/single-tenant use; a real deployment needs an
  authorization layer in front of it (see the 0.3 governance roadmap).
- `_rank()`'s score always includes `node.importance * 0.15` (see
  `contextos/orchestration/orchestrator.py`), with no minimum relevance floor before
  that term applies — a sufficiently important node can clear the ranking bar for a
  task it has near-zero lexical overlap with, which shows up as real precision loss on
  small corpora. `examples/evaluation_suite.py` demonstrates this rather than hiding
  it; tightening the relevance/importance balance is open, not yet done.
- `ContextOSStore` (the LangGraph adapter) filters/paginates `search()`/
  `list_namespaces()` in Python after a 200-node-capped `ContextStore.search()` call —
  the same ceiling `apply_tiering_policy()` has, not pushed down to storage.

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

- [x] LangGraph example (`examples/langgraph_integration.py`)
- [x] LangGraph state and store adapter (`ContextOSStore(BaseStore)`; plugs into
      `StateGraph.compile(store=...)`; validated against the real `BaseStore` API)
- [x] MCP context server (`contextos.integrations.mcp_server.build_context_server()`;
      `contextos-mcp` CLI entry point; validated with a real MCP `ClientSession`)
- [x] A2A context exchange envelope (`contextos.integrations.a2a`, using the official
      `a2a-sdk` protobuf types; verified against the real JSON wire format)
- [x] Framework-neutral evaluation suite (`contextos.evaluation.run_eval_suite()` --
      precision/recall/f1/latency against `assemble()`, no optional extras needed)

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
