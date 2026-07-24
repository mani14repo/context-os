import pytest

pytest.importorskip("langgraph")

from contextos import ContextOS
from contextos.integrations.langgraph import ContextOSStore


@pytest.fixture
def store() -> ContextOSStore:
    return ContextOSStore(ContextOS())


@pytest.mark.asyncio
async def test_put_and_get_round_trip(store: ContextOSStore) -> None:
    await store.aput(("user1", "memories"), "fact1", {"memory": "Will likes ai"})
    item = await store.aget(("user1", "memories"), "fact1")
    assert item is not None
    assert item.value == {"memory": "Will likes ai"}
    assert item.namespace == ("user1", "memories")
    assert item.key == "fact1"


@pytest.mark.asyncio
async def test_put_upserts_existing_key(store: ContextOSStore) -> None:
    await store.aput(("user1", "memories"), "fact1", {"memory": "v1"})
    await store.aput(("user1", "memories"), "fact1", {"memory": "v2"})
    item = await store.aget(("user1", "memories"), "fact1")
    assert item is not None
    assert item.value == {"memory": "v2"}


@pytest.mark.asyncio
async def test_get_missing_key_returns_none(store: ContextOSStore) -> None:
    assert await store.aget(("user1", "memories"), "nope") is None


@pytest.mark.asyncio
async def test_delete_removes_item(store: ContextOSStore) -> None:
    await store.aput(("user1", "memories"), "fact1", {"memory": "x"})
    await store.adelete(("user1", "memories"), "fact1")
    assert await store.aget(("user1", "memories"), "fact1") is None


@pytest.mark.asyncio
async def test_search_returns_items_under_namespace(store: ContextOSStore) -> None:
    await store.aput(("user1", "memories"), "fact1", {"memory": "likes ai"})
    await store.aput(("user1", "memories"), "fact2", {"memory": "dislikes java"})
    await store.aput(("user1", "other"), "fact3", {"memory": "unrelated"})

    results = await store.asearch(("user1", "memories"))
    keys = {item.key for item in results}
    assert keys == {"fact1", "fact2"}


@pytest.mark.asyncio
async def test_search_respects_tenant_isolation(store: ContextOSStore) -> None:
    await store.aput(("user1", "memories"), "fact1", {"memory": "user1 data"})
    results = await store.asearch(("user2", "memories"))
    assert results == []


@pytest.mark.asyncio
async def test_list_namespaces_with_prefix(store: ContextOSStore) -> None:
    await store.aput(("user1", "memories"), "fact1", {"memory": "a"})
    await store.aput(("user1", "preferences"), "pref1", {"theme": "dark"})

    namespaces = await store.alist_namespaces(prefix=("user1",))
    assert set(namespaces) == {("user1", "memories"), ("user1", "preferences")}


@pytest.mark.asyncio
async def test_sync_batch_raises_not_implemented(store: ContextOSStore) -> None:
    with pytest.raises(NotImplementedError):
        store.batch([])
