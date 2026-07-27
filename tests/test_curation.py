import pytest

from contextos import ContextNode, ContextOS, MemoryType
from contextos.curation import curate, find_similar
from contextos.models import ContextQuery

_A = "Use exponential backoff when retrying API calls to avoid hitting rate limits."
_A_PARAPHRASE = "Use exponential backoff for retries to avoid rate limits on API calls."
_UNRELATED = "The invoice for Q3 is now overdue by two weeks."


@pytest.mark.asyncio
async def test_find_similar_finds_near_duplicate_above_threshold() -> None:
    os = ContextOS()
    node = await os.ingest(
        ContextNode(tenant_id="t1", node_type="insight", memory_type=MemoryType.SEMANTIC, content=_A)
    )
    await os.ingest(
        ContextNode(tenant_id="t1", node_type="insight", memory_type=MemoryType.SEMANTIC, content=_UNRELATED)
    )

    matches = await find_similar(os, "t1", _A_PARAPHRASE, threshold=0.5)

    assert len(matches) == 1
    assert matches[0].node.id == node.id
    assert matches[0].similarity >= 0.5


@pytest.mark.asyncio
async def test_find_similar_excludes_unrelated_content() -> None:
    os = ContextOS()
    await os.ingest(
        ContextNode(tenant_id="t1", node_type="insight", memory_type=MemoryType.SEMANTIC, content=_UNRELATED)
    )

    matches = await find_similar(os, "t1", _A, threshold=0.5)

    assert matches == []


@pytest.mark.asyncio
async def test_curate_merges_into_near_duplicate_instead_of_duplicating() -> None:
    os = ContextOS()
    existing = await os.ingest(
        ContextNode(tenant_id="t1", node_type="insight", memory_type=MemoryType.SEMANTIC, content=_A)
    )
    candidate = ContextNode(
        tenant_id="t1", node_type="insight", memory_type=MemoryType.SEMANTIC, content=_A_PARAPHRASE
    )

    result = await curate(os, "t1", candidate, merge_threshold=0.5)

    assert result.id == existing.id
    assert result.metadata["feedback_helpful_count"] == 1
    all_nodes = await os.search(ContextQuery(tenant_id="t1", query="", max_results=50))
    assert len(all_nodes) == 1  # merged, not duplicated


@pytest.mark.asyncio
async def test_curate_ingests_as_new_when_nothing_similar() -> None:
    os = ContextOS()
    await os.ingest(
        ContextNode(tenant_id="t1", node_type="insight", memory_type=MemoryType.SEMANTIC, content=_UNRELATED)
    )
    candidate = ContextNode(tenant_id="t1", node_type="insight", memory_type=MemoryType.SEMANTIC, content=_A)

    result = await curate(os, "t1", candidate, merge_threshold=0.9)

    assert result.id == candidate.id
    all_nodes = await os.search(ContextQuery(tenant_id="t1", query="", max_results=50))
    assert len(all_nodes) == 2
