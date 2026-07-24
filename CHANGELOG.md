# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- `azure-blob` extra was missing `aiohttp`: `azure-storage-blob`'s async client needs
  it to build its async transport but doesn't pull it in transitively, so
  `AzureBlobArtifactStore` raised `ModuleNotFoundError: No module named 'aiohttp'` in
  any environment where nothing else happened to install `aiohttp` first (this went
  unnoticed locally because `aioboto3`, from the `s3` extra, pulls it in via
  `aiobotocore` -- the CI `test-azure-blob` job installs `azure-blob` alone and caught
  it). Added `aiohttp>=3.8,<4` to the `azure-blob` extra; reproduced the failure and
  confirmed the fix in an isolated venv installing only `dev,azure-blob`, matching
  exactly what CI installs. Also spot-checked every other extra (`postgres`, `redis`,
  `s3`, `langgraph`, `otel`, `mcp`) the same way -- installed alone, in a fresh venv --
  and found no other missing transitive dependencies.
- `tests/test_mcp_server.py`, `tests/test_langgraph_store.py`, and
  `tests/test_a2a_envelope.py` were never actually running in CI: the main `test` job
  only installs the `dev` extra, so `pytest.importorskip("mcp"/"langgraph"/"a2a")`
  silently skipped all three every run instead of exercising them -- the same class of
  gap as the `aiohttp` issue above, just quieter (a skip, not a failure). Added a
  `test-integrations` CI job installing `dev,langgraph,mcp,a2a` together (none of
  these three need an external service); verified the combined install has no
  dependency conflicts and all 18 tests pass under it before relying on it.

### Added

- LangGraph `BaseStore` adapter: `contextos.integrations.langgraph.ContextOSStore`
  implements LangGraph's `BaseStore` (`abatch`; sync `batch()` raises
  `NotImplementedError` since ContextOS is async-only), so it plugs directly into
  `StateGraph.compile(store=...)` as cross-thread/long-term memory backed by whatever
  ContextStore ContextOS is configured with. `namespace[0]` maps to `tenant_id`;
  get/put/delete use a deterministic `uuid5(namespace, key)` node id rather than a
  search. Validated against the real public `BaseStore` API
  (`aget`/`aput`/`adelete`/`asearch`/`alist_namespaces`), including tenant isolation
  and a real `StateGraph` run in `examples/langgraph_store.py`.
- A2A context exchange envelope: `contextos.integrations.a2a`
  (`pip install -e ".[a2a]"`) -- `context_package_to_artifact()` and
  `a2a_message_to_context_node()`, built on the official `a2a-sdk` protobuf types
  rather than a hand-rolled approximation of the wire format. Verified against real
  `a2a.types.Artifact`/`Message` objects and their actual JSON serialization via
  `google.protobuf.json_format.MessageToDict` (camelCase field names, `Struct`-typed
  metadata), not just Python-level assertions.
- Framework-neutral evaluation suite: `contextos.evaluation` (`EvalCase`, `EvalResult`,
  `EvalReport`, `run_eval_suite()`) scores `ContextOS.assemble()`'s precision/recall/f1/
  latency against known-correct node ids per task. No optional extras needed. Test
  cases use hand-computed expected metrics, not just "did it run" checks; this also
  surfaced a real ranking finding (`examples/evaluation_suite.py`): `_rank()`'s
  importance term has no minimum-relevance floor, so precision comes out below 1.0
  even on off-topic tasks on small corpora -- now documented under "Known limitations"
  rather than left to be discovered by a user.
- MCP context server: `contextos.integrations.mcp_server.build_context_server()`
  (`pip install -e ".[mcp]"`) wraps any `ContextOS` instance as an MCP server exposing
  `ingest_context`/`search_context`/`assemble_context`/`link_context`/`move_context`/
  `context_history` as tools, plus a `contextos-mcp` console script for a stdio server
  over an in-memory store. Validated with a real MCP `ClientSession` connected over
  in-memory streams (`mcp.shared.memory.create_connected_server_and_client_session`),
  not by calling the wrapped Python functions directly -- actual protocol round trips,
  including a real tool-level error path (invalid `memory_type` -> `isError=True`).

- `SQLiteContextStore`: a stdlib-only, persisted `ContextStore`/`GraphStore`/`TierManager`/
  `AccessLog` implementation, a drop-in replacement for `InMemoryContextStore`.
- Examples: LangGraph `StateGraph` integration, context persisting across process restarts,
  swapping store/compactor backends with unchanged calling code, and the compaction
  ladder's automatic budget-driven downgrade (`examples/`).
- `contextos.search.score_node`: shared lexical scoring so every `ContextStore`
  implementation ranks identically.
- **Immutable node history**: `ContextStore.put_node()` now archives the prior version
  on update instead of overwriting it, and increments `ContextNode.version`. Retrieve
  history via the new `ContextStore.get_history()` protocol method or
  `ContextOS.history()`.
- **Temporal validity enforcement**: `ContextQuery.as_of` (defaults to now); `search()`
  and graph traversal now exclude nodes and edges outside their `valid_from`/`valid_to`
  window.
- **Access logging**: new `AccessLog` protocol (`record`/`last_accessed`), implemented by
  both stores. `ContextOrchestrator.assemble()` records access for every node included
  in the returned package.
- **Automatic tiering**: `contextos.tiering.suggest_tier()` and
  `ContextOS.apply_tiering_policy(tenant_id)`, using access recency, importance, and
  `active_workflow`/`retention_required` metadata flags.
- `ContextOS` constructor now also accepts `access_log` as an independently swappable
  collaborator (alongside `store`, `graph`, `compactor`, `tier_manager`).
- `PostgresContextStore` (`contextos.storage.postgres`, `pip install -e ".[postgres]"`):
  a `ContextStore`/`GraphStore`/`TierManager`/`AccessLog` implementation backed by
  PostgreSQL + pgvector, ranking search results by real cosine-distance vector
  similarity instead of lexical overlap. Validated against a live `pgvector/pgvector`
  container, not just unit-tested with fakes.
- New `EmbeddingProvider` protocol and `contextos.embeddings.HashingEmbeddingProvider`,
  a dependency-free deterministic reference implementation (captures lexical overlap,
  not semantic meaning -- swap in a real model via the same protocol).
- `contextos.search`: extracted `node_haystack()`/`passes_filters()` so all three
  stores share identical filtering logic regardless of how each ranks relevance.
- `examples/postgres_pgvector_store.py`; docker-compose and CI now include a Postgres
  service for the adapter's test suite (`tests/test_postgres_store.py`, skipped
  automatically when `asyncpg` isn't installed or no DSN is configured).
- `RedisCachedContextStore` (`contextos.storage.redis_cache`, `pip install -e ".[redis]"`):
  a TTL read-through cache decorator for `get_node()`, wrapping any store implementing
  the new `FullContextStore` combined protocol. Invalidates on `put_node()`/`move()`/
  `delete_node()`; `search()`/`neighbors()` pass straight through uncached. Validated
  against a live Redis container, including TTL expiry and cache-hit counting, not
  just asserted with fakes.
- `contextos.protocols.FullContextStore`: a named union of `ContextStore`, `GraphStore`,
  `TierManager`, and `AccessLog` for typing wrappers/decorators that need the full
  surface (every built-in store already satisfies it).
- `examples/redis_cache.py`; docker-compose and CI now include a Redis service for
  the adapter's test suite (`tests/test_redis_cache.py`, skipped automatically when
  `redis` isn't installed or no URL is configured).
- New `ArtifactStore` protocol (`put`/`get`/`delete`), plus `S3ArtifactStore`
  (`contextos.storage.s3_artifacts`, `pip install -e ".[s3]"`, via `aioboto3` -- works
  against Amazon S3 or any S3-compatible service such as MinIO) and
  `AzureBlobArtifactStore` (`contextos.storage.azure_artifacts`,
  `pip install -e ".[azure-blob]"`, via `azure-storage-blob` -- works against Azure
  Blob Storage or the Azurite emulator). This is the "graph-content separation"
  design principle made real: `ContextOS.store_artifact()`/`load_artifact()` write/read
  large original content and hand back a pointer for `ContextNode.content_pointer`.
  Validated against live MinIO and Azurite containers, including a real Azurite
  compatibility issue (`--skipApiVersionCheck` needed against recent SDK releases) hit
  and fixed during that validation, not just documented from a changelog somewhere.
- `contextos.tracing.start_span()`: a no-op-safe OpenTelemetry span helper, wrapping
  `ContextOS.ingest()`/`link()`/`compact()`/`move()`/`apply_tiering_policy()` and
  `ContextOrchestrator.assemble()`. Does nothing unless the new `otel` extra
  (`opentelemetry-api`/`opentelemetry-sdk`) is installed and the application configures
  an SDK/exporter -- verified with a real `TracerProvider` + `ConsoleSpanExporter` in
  `examples/opentelemetry_tracing.py`, not just by inspecting the no-op path.
- `ContextOS` constructor now also accepts `artifacts` (no in-process default, unlike
  the other five collaborators -- `InMemoryContextStore`/`SQLiteContextStore` don't
  implement `ArtifactStore`).
- Verified the core package (`pip install -e .`, no extras) still imports and passes
  its full test suite with zero optional dependencies installed -- the six adapters
  added across this release are genuinely optional, not soft-required.

## [0.1.0] - 2026-07-24

### Added

- Memory taxonomy (`working`, `semantic`, `episodic`, `operational`, `procedural`, `artifact`)
  and typed graph relationships via `ContextNode`/`ContextEdge`.
- Temporal context nodes with versioning fields and multi-tenant isolation.
- In-memory reference `ContextStore`/`GraphStore` implementation for prototypes and tests.
- Progressive compaction contract with six representation levels (metadata through original).
- Token-budgeted context assembly via `ContextOrchestrator`, including relevance- and
  graph-proximity-aware ranking and automatic fallback from hot/warm to all storage tiers
  when no direct matches are found.
- `Compactor` protocol and constructor-level injection of `store`, `graph`, `compactor`,
  and `tier_manager` on `ContextOS` for custom backends.
- Optional FastAPI service (`contextos-api`) and Docker entry point.
- Test suite and GitHub Actions CI (ruff + pytest).

### Known limitations

See the "Known Limitations" section in `README.md`. Notably: temporal validity
(`valid_from`/`valid_to`) is modeled but not enforced by search, node updates do not
create new versions, there is no access logging or automatic tiering policy, and there
is no ingestion pipeline (classification, entity extraction, embeddings) or vector search.
