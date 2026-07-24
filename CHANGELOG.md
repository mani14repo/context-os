# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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
