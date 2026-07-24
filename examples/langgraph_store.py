"""ContextOS as LangGraph's cross-thread/long-term memory store.

Requires: pip install -e ".[langgraph]"

examples/langgraph_integration.py showed calling ContextOS.assemble()/ingest()
directly from graph nodes -- that's per-thread context retrieval. This example is
different: `ContextOSStore` implements LangGraph's `BaseStore` interface, so it plugs
into `StateGraph.compile(store=...)` and becomes the backing store for LangGraph's own
cross-thread memory APIs (`get_store().aput()`/`asearch()` inside a node), persisted
through whatever ContextStore ContextOS is configured with instead of LangGraph's
default in-memory store.
"""

import asyncio
from typing import TypedDict

from langgraph.config import get_store
from langgraph.graph import END, START, StateGraph

from contextos import ContextOS
from contextos.integrations.langgraph import ContextOSStore

USER_ID = "demo-user"


class AgentState(TypedDict):
    key: str
    message: str
    recalled: list[str]


async def remember(state: AgentState) -> dict:
    store = get_store()
    await store.aput((USER_ID, "preferences"), state["key"], {"text": state["message"]})
    return {}


async def recall(state: AgentState) -> dict:
    store = get_store()
    items = await store.asearch((USER_ID, "preferences"))
    return {"recalled": [item.value["text"] for item in items]}


def build_graph(store: ContextOSStore):
    graph = StateGraph(AgentState)
    graph.add_node("remember", remember)
    graph.add_node("recall", recall)
    graph.add_edge(START, "remember")
    graph.add_edge("remember", "recall")
    graph.add_edge("recall", END)
    return graph.compile(store=store)


async def main() -> None:
    context_os = ContextOS()
    store = ContextOSStore(context_os)
    app = build_graph(store)

    result = await app.ainvoke({"key": "editor", "message": "I prefer vim keybindings", "recalled": []})
    print("Turn 1 recalled:", result["recalled"])

    # A second turn (a different thread, same user, different key) still sees what
    # turn 1 remembered -- it's stored through ContextOS, not the graph's
    # per-invocation state, so recall accumulates across separate ainvoke() calls.
    result2 = await app.ainvoke({"key": "theme", "message": "Dark theme by default", "recalled": []})
    print("Turn 2 recalled:", result2["recalled"])


if __name__ == "__main__":
    asyncio.run(main())
