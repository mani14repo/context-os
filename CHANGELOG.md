# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
