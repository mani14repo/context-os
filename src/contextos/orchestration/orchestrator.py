from __future__ import annotations

import math
from collections.abc import Sequence
from uuid import UUID

from contextos.compaction.simple import SimpleCompactor
from contextos.models import (
    CompressionLevel,
    ContextNode,
    ContextPackage,
    ContextQuery,
    ContextRequest,
    RankedContext,
    StorageTier,
)
from contextos.protocols import AccessLog, Compactor, ContextStore, GraphStore
from contextos.text import tokenize
from contextos.tracing import start_span

_HOT_WARM = frozenset({StorageTier.HOT, StorageTier.WARM})


class ContextOrchestrator:
    def __init__(
        self,
        store: ContextStore,
        graph: GraphStore,
        compactor: Compactor | None = None,
        access_log: AccessLog | None = None,
    ):
        self.store = store
        self.graph = graph
        self.compactor = compactor or SimpleCompactor()
        self.access_log = access_log

    async def assemble(self, request: ContextRequest) -> ContextPackage:
        with start_span(
            "contextos.assemble",
            tenant_id=request.tenant_id,
            agent=request.agent,
            token_budget=request.token_budget,
        ) as span:
            query = ContextQuery(
                tenant_id=request.tenant_id,
                query=request.task,
                memory_types=request.memory_scopes,
                tiers=_HOT_WARM,
                max_results=30,
                minimum_confidence=request.minimum_confidence,
                graph_depth=request.graph_depth,
            )
            direct = list(await self.store.search(query))
            if not direct:
                # Nothing in hot/warm tiers matched; widen to cold/archive before giving up.
                fallback_query = query.model_copy(update={"tiers": set()})
                direct = list(await self.store.search(fallback_query))
            related = list(
                await self.graph.neighbors(
                    request.tenant_id, [node.id for node in direct[:5]], request.graph_depth
                )
            )
            direct_ids = {node.id for node in direct}
            candidates = self._dedupe([*direct, *related])
            ranked = self._rank(candidates, request.task, direct_ids)
            selected, token_count, tokens_saved = await self._fit_budget(ranked, request.token_budget)
            if self.access_log is not None:
                for item in selected:
                    await self.access_log.record(
                        request.tenant_id, item.node.id, request.agent, request.task
                    )
            span.set_attribute("contextos.item_count", len(selected))
            span.set_attribute("contextos.token_count", token_count)
            span.set_attribute("contextos.tokens_saved", tokens_saved)
        return ContextPackage(
            request=request,
            items=selected,
            token_count=token_count,
            tokens_saved=tokens_saved,
            missing_context=[] if selected else ["No relevant context found"],
            provenance=[item.node.id for item in selected],
        )

    @staticmethod
    def _dedupe(nodes: Sequence[ContextNode]) -> list[ContextNode]:
        return list({node.id: node for node in nodes}.values())

    @staticmethod
    def _relevance(query_terms: set[str], node: ContextNode) -> float:
        haystack = " ".join(filter(None, [node.title, node.summary, node.content]))
        node_terms = tokenize(haystack)
        if not query_terms or not node_terms:
            return 0.0
        overlap = len(query_terms & node_terms)
        return overlap / math.sqrt(len(query_terms) * len(node_terms))

    @staticmethod
    def _rank(nodes: Sequence[ContextNode], task: str, direct_ids: set[UUID]) -> list[RankedContext]:
        tier_bonus = {
            StorageTier.HOT: 0.15,
            StorageTier.WARM: 0.10,
            StorageTier.COLD: 0.03,
            StorageTier.ARCHIVE: 0.0,
        }
        query_terms = tokenize(task)
        ranked = []
        for node in nodes:
            relevance = ContextOrchestrator._relevance(query_terms, node)
            # Nodes found directly by the query are treated as one hop closer than
            # nodes only reached through graph expansion; real depth-weighting would
            # require GraphStore.neighbors() to expose traversal depth.
            graph_proximity = 1.0 if node.id in direct_ids else 0.5
            score = (
                relevance * 0.30
                + graph_proximity * 0.20
                + node.importance * 0.15
                + node.confidence * 0.10
                + node.source_authority * 0.15
                + tier_bonus[node.storage_tier]
            )
            ranked.append(
                RankedContext(
                    node=node,
                    score=round(score, 4),
                    reasons=[
                        "relevance",
                        "graph_proximity",
                        "importance",
                        "confidence",
                        "source_authority",
                        "storage_tier",
                    ],
                )
            )
        return sorted(ranked, key=lambda item: item.score, reverse=True)

    async def _fit_budget(
        self, ranked: Sequence[RankedContext], token_budget: int
    ) -> tuple[list[RankedContext], int, int]:
        selected: list[RankedContext] = []
        used = 0
        saved = 0
        for item in ranked:
            representation = await self.compactor.compact(item.node, CompressionLevel.COMPACT)
            cost = representation.token_count or 0
            if used + cost > token_budget:
                representation = await self.compactor.compact(item.node, CompressionLevel.ONE_LINE)
                cost = representation.token_count or 0
            if used + cost > token_budget:
                continue
            node = item.node.model_copy(deep=True)
            node.representations.append(representation)
            selected.append(item.model_copy(update={"node": node}))
            used += cost
            saved += representation.tokens_saved or 0
        return selected, used, saved
