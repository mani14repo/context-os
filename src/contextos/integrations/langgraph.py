from __future__ import annotations

import uuid
from collections.abc import Iterable

from langgraph.store.base import (
    BaseStore,
    GetOp,
    Item,
    ListNamespacesOp,
    Op,
    PutOp,
    Result,
    SearchItem,
    SearchOp,
)

from contextos.library import ContextOS
from contextos.models import ContextNode, ContextPackage, ContextQuery, MemoryType

__all__ = ["ContextOSStore", "to_prompt_context"]


def to_prompt_context(package: ContextPackage) -> str:
    """Flatten a ContextPackage into a prompt-ready string for a LangGraph node.

    ContextOS.assemble() already does the retrieval, ranking, and budget-fitting a
    LangGraph node needs -- this is the one piece of glue an LLM prompt actually
    requires beyond that: turning structured `RankedContext` items into text. There
    is intentionally no other LangGraph-specific machinery here; build state graphs
    directly against `ContextOS.assemble()`/`ContextOS.ingest()` as shown in
    examples/langgraph_integration.py.
    """
    if not package.items:
        return "No relevant context found."
    lines = []
    for item in package.items:
        representation = item.node.representations[-1] if item.node.representations else None
        content = representation.content if representation else (item.node.summary or item.node.title)
        lines.append(f"- ({item.node.memory_type.value}) {content or ''}".rstrip())
    return "\n".join(lines)


def _tenant_id(namespace: tuple[str, ...]) -> str:
    if not namespace:
        raise ValueError("ContextOSStore requires a non-empty namespace (namespace[0] is the tenant_id)")
    return namespace[0]


def _node_id(namespace: tuple[str, ...], key: str) -> uuid.UUID:
    # Deterministic so get/put/delete are direct ContextStore.get_node()/put_node()/
    # delete_node() calls by id, not a search -- uuid.NAMESPACE_URL is a fixed stdlib
    # constant, not something invented here, so this is reproducible across processes.
    return uuid.uuid5(uuid.NAMESPACE_URL, f"contextos-langgraph-store:{'/'.join(namespace)}:{key}")


def _node_to_item(node: ContextNode) -> Item:
    return Item(
        value=node.metadata.get("_langgraph_value", {}),
        key=node.metadata.get("_langgraph_key", ""),
        namespace=tuple(node.metadata.get("_langgraph_namespace", [node.tenant_id])),
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


class ContextOSStore(BaseStore):
    """LangGraph `BaseStore` backed by a `ContextOS` instance -- cross-thread/
    long-term memory persisted through whatever ContextStore ContextOS is configured
    with (in-memory, SQLite, Postgres+pgvector, ...) instead of LangGraph's own stores.

    Maps LangGraph's `(namespace, key)` addressing onto ContextOS: `namespace[0]`
    becomes the ContextOS `tenant_id` (LangGraph namespaces conventionally start with
    a user/thread id, which lines up with ContextOS's tenant scoping), and the node id
    is derived deterministically from the full namespace + key via `uuid5`, so
    get/put/delete are direct `ContextStore.get_node()`/`put_node()`/`delete_node()`
    calls rather than a search.

    `search()`/`list_namespaces()` page through a tenant's nodes (capped by
    `ContextQuery.max_results`, same 200-node-per-call ceiling as
    `ContextOS.apply_tiering_policy()`) and filter/paginate in Python -- exact
    prefix/filter matching isn't pushed down to storage. Every stored item is tagged
    `node_type="langgraph_item"` by default so it doesn't get mixed into normal
    `ContextOS.search()`/`assemble()` calls unless you ask for that node type.

    ContextOS is fully async, so only the async `BaseStore` methods are implemented
    (`aget`/`aput`/`adelete`/`asearch`/`alist_namespaces`, via `abatch`); the sync
    `batch()` raises `NotImplementedError`.
    """

    def __init__(
        self,
        context_os: ContextOS,
        *,
        node_type: str = "langgraph_item",
        memory_type: MemoryType = MemoryType.WORKING,
    ) -> None:
        self._context_os = context_os
        self._node_type = node_type
        self._memory_type = memory_type

    def batch(self, ops: Iterable[Op]) -> list[Result]:
        raise NotImplementedError(
            "ContextOSStore is async-only, matching ContextOS itself -- use the "
            "async store methods (aget/aput/adelete/asearch/alist_namespaces)."
        )

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:
        results: list[Result] = []
        for op in ops:
            if isinstance(op, GetOp):
                results.append(await self._get(op))
            elif isinstance(op, PutOp):
                await self._put(op)
                results.append(None)
            elif isinstance(op, SearchOp):
                results.append(await self._search(op))
            elif isinstance(op, ListNamespacesOp):
                results.append(await self._list_namespaces(op))
            else:
                raise TypeError(f"Unsupported LangGraph store op: {type(op).__name__}")
        return results

    async def _get(self, op: GetOp) -> Item | None:
        tenant_id = _tenant_id(op.namespace)
        node = await self._context_os.store.get_node(tenant_id, _node_id(op.namespace, op.key))
        return _node_to_item(node) if node is not None else None

    async def _put(self, op: PutOp) -> None:
        tenant_id = _tenant_id(op.namespace)
        node_id = _node_id(op.namespace, op.key)
        if op.value is None:
            await self._context_os.store.delete_node(tenant_id, node_id)
            return
        await self._context_os.ingest(
            ContextNode(
                id=node_id,
                tenant_id=tenant_id,
                node_type=self._node_type,
                memory_type=self._memory_type,
                title=op.key,
                content=str(op.value),
                metadata={
                    "_langgraph_namespace": list(op.namespace),
                    "_langgraph_key": op.key,
                    "_langgraph_value": op.value,
                },
            )
        )

    async def _search(self, op: SearchOp) -> list[SearchItem]:
        tenant_id = _tenant_id(op.namespace_prefix)
        nodes = await self._context_os.store.search(
            ContextQuery(
                tenant_id=tenant_id,
                query=op.query or "",
                node_types={self._node_type},
                max_results=200,
            )
        )
        prefix = list(op.namespace_prefix)
        items: list[SearchItem] = []
        for node in nodes:
            namespace = node.metadata.get("_langgraph_namespace", [])
            if namespace[: len(prefix)] != prefix:
                continue
            value = node.metadata.get("_langgraph_value", {})
            if op.filter and any(value.get(k) != v for k, v in op.filter.items()):
                continue
            items.append(
                SearchItem(
                    namespace=tuple(namespace),
                    key=node.metadata.get("_langgraph_key", ""),
                    value=value,
                    created_at=node.created_at,
                    updated_at=node.updated_at,
                )
            )
        return items[op.offset : op.offset + op.limit]

    async def _list_namespaces(self, op: ListNamespacesOp) -> list[tuple[str, ...]]:
        prefix: tuple[str, ...] = ()
        for condition in op.match_conditions or []:
            if condition.match_type == "prefix":
                prefix = tuple(condition.path)
        tenant_id = prefix[0] if prefix else None
        if tenant_id is None:
            raise ValueError(
                "ContextOSStore.alist_namespaces() requires a prefix match condition "
                "whose first segment is the tenant_id -- unscoped listing across all "
                "tenants isn't supported."
            )
        nodes = await self._context_os.store.search(
            ContextQuery(tenant_id=tenant_id, query="", node_types={self._node_type}, max_results=200)
        )
        namespaces = {
            tuple(node.metadata["_langgraph_namespace"])
            for node in nodes
            if "_langgraph_namespace" in node.metadata
            and tuple(node.metadata["_langgraph_namespace"])[: len(prefix)] == prefix
        }
        if op.max_depth is not None:
            namespaces = {ns[: op.max_depth] for ns in namespaces}
        sorted_namespaces = sorted(namespaces)
        return sorted_namespaces[op.offset : op.offset + op.limit]
