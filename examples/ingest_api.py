"""Ingesting JSON records from a REST API into ContextOS.

Needs `pip install -e ".[http]"`.

`APIExtractor` fetches a JSON endpoint and maps each record to a ContextNode via a
configurable field mapping -- this covers most REST APIs and JSON-shaped database
query results directly, without a source-specific extractor for every vendor. This
example runs a tiny local JSON server so the script is self-contained; point `url`
at any real API and the same code applies.
"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from contextos import ContextOS
from contextos.ingestion.api import APIExtractor

_TICKETS = [
    {"id": 101, "title": "Printer offline", "content": "The 3rd floor printer is jammed and offline."},
    {"id": 102, "title": "VPN drops", "content": "VPN disconnects roughly once an hour for remote staff."},
]


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps(_TICKETS).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


async def main() -> None:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        context_os = ContextOS()
        extractor = APIExtractor(
            f"http://127.0.0.1:{server.server_port}/tickets", id_field="id"
        )
        nodes = await context_os.ingest_source(extractor, tenant_id="acme")

        print(f"ingest_source() pulled {len(nodes)} record(s) from the API:")
        for node in nodes:
            print(f"  #{node.metadata['source_id']} {node.title}: {node.content}")
    finally:
        server.shutdown()
        thread.join()


if __name__ == "__main__":
    asyncio.run(main())
