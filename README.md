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

A complete graph example is available in `examples/basic.py`.

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
├── storage/memory.py        # Reference implementation
├── compaction/simple.py     # Deterministic fallback compactor
├── orchestration/           # Retrieval, ranking, budget fitting
├── api/app.py               # Optional FastAPI service
└── integrations/            # Runtime adapters belong here
```

## Extending ContextOS

`ContextOS` accepts four independently swappable collaborators, each defined as a
`Protocol` in `contextos.protocols` so a custom implementation only needs to match
the method signatures — no base class to inherit:

```python
from contextos import ContextOS

os = ContextOS(
    store=MyPostgresStore(),      # implements contextos.protocols.ContextStore
    graph=MyGraphBackend(),       # implements contextos.protocols.GraphStore, defaults to `store`
    compactor=MyLLMCompactor(),   # implements contextos.protocols.Compactor, defaults to SimpleCompactor
    tier_manager=MyTierManager(), # implements contextos.protocols.TierManager, defaults to `store`
)
```

If you only override `store`, `graph` and `tier_manager` fall back to it automatically,
matching the built-in `InMemoryContextStore`, which implements all three protocols at once.
See `CONTRIBUTING.md` for the expectation that new storage or model providers implement
these protocols rather than coupling the core package to a specific vendor.

## Known limitations

The reference (`InMemoryContextStore`) implementation intentionally keeps v0.1 small.
Known gaps, tracked as GitHub issues:

- `valid_from`/`valid_to` are modeled on `ContextNode` but not enforced during search or
  graph traversal.
- `put_node` overwrites in place; updates do not create a new `version` or retain history,
  so the "context is immutable by default" design principle is not yet enforced.
- No access logging, so storage tiering has no automatic recency/frequency signal to act on;
  tier changes are manual via `ContextOS.move()`.
- No ingestion pipeline: `ContextOS.ingest()` stores the `ContextNode` you hand it as-is —
  there is no automatic classification, entity extraction, or embedding generation.
- No vector/semantic search: `InMemoryContextStore.search()` uses lexical token overlap,
  not embeddings.
- No governance layer (authorization, retention, redaction) — see `SECURITY.md`.

## Roadmap

### 0.1 — Foundation

- [x] Memory taxonomy
- [x] Temporal nodes and edges
- [x] Multi-tenant in-memory store
- [x] Progressive compaction contract
- [x] Token-budgeted context assembly
- [x] FastAPI and Docker entry points
- [x] Tests and GitHub Actions

### 0.2 — Production adapters

- [ ] PostgreSQL + pgvector store
- [ ] Redis working-memory/cache adapter
- [ ] S3/Azure Blob artifact adapter
- [ ] OpenTelemetry traces and access logs
- [ ] Pluggable embedding and reranking providers

### 0.3 — Governance

- [ ] Authorization decision point and ABAC hooks
- [ ] Retention rules and legal-hold support
- [ ] Context redaction and classification
- [ ] Contradiction and supersession workflows
- [ ] Immutable provenance manifests

### 0.4 — Agent ecosystem

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
