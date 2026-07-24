from __future__ import annotations

from fastapi import FastAPI, HTTPException

from contextos.library import ContextOS
from contextos.models import ContextEdge, ContextNode, ContextPackage, ContextQuery, ContextRequest

app = FastAPI(title="ContextOS", version="0.1.0")
os = ContextOS()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/context", response_model=ContextNode)
async def ingest(node: ContextNode) -> ContextNode:
    return await os.ingest(node)


@app.post("/v1/context/link", response_model=ContextEdge)
async def link(edge: ContextEdge) -> ContextEdge:
    try:
        return await os.link(edge)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/context/search", response_model=list[ContextNode])
async def search(query: ContextQuery) -> list[ContextNode]:
    return await os.search(query)


@app.post("/v1/context/assemble", response_model=ContextPackage)
async def assemble(request: ContextRequest) -> ContextPackage:
    return await os.assemble(request)


def main() -> None:
    import uvicorn

    uvicorn.run("contextos.api.app:app", host="0.0.0.0", port=8080, reload=False)
