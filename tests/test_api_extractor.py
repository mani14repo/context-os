import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytest.importorskip("httpx")

from contextos.ingestion.api import APIExtractor

_BARE_LIST = [
    {"id": 1, "title": "First ticket", "content": "Printer is broken on the 3rd floor."},
    {"id": 2, "title": "Second ticket", "content": "VPN keeps disconnecting every hour."},
]
_NESTED = {"data": {"items": _BARE_LIST}, "page": 1}
_SINGLE = {"id": 7, "title": "Single record", "content": "Just one object, not a list."}


def _make_handler(routes: dict[str, object]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path not in routes:
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(routes[self.path]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass  # keep test output quiet

    return Handler


@pytest.fixture
def json_server() -> Iterator[str]:
    """A real local HTTP server serving fixed JSON payloads -- APIExtractor makes a
    genuine HTTP request against it over a real socket, not a mocked transport."""
    routes = {"/bare-list": _BARE_LIST, "/nested": _NESTED, "/single": _SINGLE}
    server = HTTPServer(("127.0.0.1", 0), _make_handler(routes))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


@pytest.mark.asyncio
async def test_extracts_a_bare_json_list(json_server: str) -> None:
    nodes = await APIExtractor(f"{json_server}/bare-list", id_field="id").extract(tenant_id="t1")

    assert len(nodes) == 2
    assert nodes[0].title == "First ticket"
    assert nodes[0].content == "Printer is broken on the 3rd floor."
    assert nodes[0].metadata["source_id"] == 1
    assert nodes[0].metadata["source_type"] == "api"


@pytest.mark.asyncio
async def test_extracts_a_list_nested_under_records_path(json_server: str) -> None:
    nodes = await APIExtractor(f"{json_server}/nested", records_path="data.items").extract(
        tenant_id="t1"
    )

    assert len(nodes) == 2
    assert {node.title for node in nodes} == {"First ticket", "Second ticket"}


@pytest.mark.asyncio
async def test_single_object_response_yields_one_node(json_server: str) -> None:
    nodes = await APIExtractor(f"{json_server}/single").extract(tenant_id="t1")

    assert len(nodes) == 1
    assert nodes[0].content == "Just one object, not a list."


@pytest.mark.asyncio
async def test_missing_content_field_falls_back_to_json_dump(json_server: str) -> None:
    nodes = await APIExtractor(f"{json_server}/bare-list", content_field="does_not_exist").extract(
        tenant_id="t1"
    )

    assert len(nodes) == 2
    assert "Printer is broken" in (nodes[0].content or "")


@pytest.mark.asyncio
async def test_missing_records_path_raises_keyerror(json_server: str) -> None:
    with pytest.raises(KeyError):
        await APIExtractor(f"{json_server}/nested", records_path="data.missing").extract(
            tenant_id="t1"
        )


@pytest.mark.asyncio
async def test_non_2xx_status_raises(json_server: str) -> None:
    import httpx

    with pytest.raises(httpx.HTTPStatusError):
        await APIExtractor(f"{json_server}/does-not-exist").extract(tenant_id="t1")


@pytest.mark.asyncio
async def test_ingest_source_persists_api_records(json_server: str) -> None:
    from contextos import ContextOS

    context_os = ContextOS()
    nodes = await context_os.ingest_source(
        APIExtractor(f"{json_server}/bare-list"), tenant_id="t1"
    )

    assert len(nodes) == 2
    for node in nodes:
        stored = await context_os.store.get_node("t1", node.id)
        assert stored is not None
