"""Wire ContextOS into a LangGraph agent.

Requires: pip install -e ".[langgraph]"

ContextOS is agent-runtime-neutral: a LangGraph node is just a function that calls
`ContextOS.assemble()` to retrieve context and `ContextOS.ingest()` to persist an
outcome, same as it would from any other runtime. This example builds a three-node
graph -- retrieve context, "answer" (stubbed in place of a real LLM call so this
example has no model-provider dependency), record the outcome as episodic memory --
and runs it for two questions in a row to show the second answer benefiting from the
first turn's stored outcome.
"""

import asyncio
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from contextos import ContextNode, ContextOS, ContextRequest, MemoryType
from contextos.integrations.langgraph import to_prompt_context

TENANT_ID = "demo"
AGENT_NAME = "release-assistant"


class AgentState(TypedDict):
    task: str
    context_text: str
    answer: str


def build_graph(context_os: ContextOS):
    async def retrieve_context(state: AgentState) -> dict:
        package = await context_os.assemble(
            ContextRequest(
                tenant_id=TENANT_ID,
                task=state["task"],
                agent=AGENT_NAME,
                token_budget=500,
            )
        )
        return {"context_text": to_prompt_context(package)}

    async def answer(state: AgentState) -> dict:
        # Stand-in for a real LLM call: a production node would send
        # `state["context_text"]` and `state["task"]` to a chat model here.
        answer_text = f"Based on stored context:\n{state['context_text']}"
        return {"answer": answer_text}

    async def record_outcome(state: AgentState) -> dict:
        await context_os.ingest(
            ContextNode(
                tenant_id=TENANT_ID,
                node_type="agent_turn",
                memory_type=MemoryType.EPISODIC,
                title=state["task"],
                content=state["answer"],
                importance=0.6,
            )
        )
        return {}

    graph = StateGraph(AgentState)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("answer", answer)
    graph.add_node("record_outcome", record_outcome)
    graph.add_edge(START, "retrieve_context")
    graph.add_edge("retrieve_context", "answer")
    graph.add_edge("answer", "record_outcome")
    graph.add_edge("record_outcome", END)
    return graph.compile()


async def main() -> None:
    context_os = ContextOS()
    await context_os.ingest(
        ContextNode(
            tenant_id=TENANT_ID,
            node_type="project_convention",
            memory_type=MemoryType.SEMANTIC,
            title="Release convention",
            content="Stable releases use semantic versioning and include a changelog.",
            importance=0.9,
        )
    )

    app = build_graph(context_os)

    first = await app.ainvoke({"task": "What is required for a stable release?"})
    print("--- Turn 1 ---")
    print(first["answer"])

    # The second turn's retrieval now also sees Turn 1's outcome as episodic memory.
    second = await app.ainvoke({"task": "What did we decide about stable releases?"})
    print("\n--- Turn 2 ---")
    print(second["answer"])


if __name__ == "__main__":
    asyncio.run(main())
