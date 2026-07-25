"""Ingesting real Mattermost channel messages into ContextOS.

Needs `pip install -e ".[mattermost]"` and a running Mattermost server
(`docker compose up mattermost`). Mattermost is self-hostable, unlike most SaaS
chat products, so this connector can be exercised against a real live server
instead of a mock.

This example bootstraps an admin account, team, and channel via the REST API,
posts a couple of messages, then ingests them with MattermostExtractor. Only the
very first user ever created on a Mattermost instance can self-register when open
registration is off (the default after that first signup) -- so bootstrap always
tries to create the same fixed account and then logs in with it either way,
whether this is a fresh instance (creation succeeds) or a rerun against one that
already exists (creation 403s, login still succeeds).
"""

import asyncio
import os
import uuid

import httpx

from contextos import ContextOS
from contextos.ingestion.mattermost import MattermostExtractor

BASE_URL = os.environ.get("CONTEXTOS_MATTERMOST_URL", "http://localhost:8065")
# Same fixed identity tests/test_mattermost_extractor.py bootstraps -- sharing one
# convention means this example and the test suite can run against the same
# container without fighting over who gets to be "the first user".
_USERNAME = "ctxadmin"
_PASSWORD = "ContextOS-Test-123!"


async def _bootstrap() -> tuple[str, str]:
    """Returns (token, channel_id) for the demo admin + a fresh team/channel with two posts."""
    suffix = uuid.uuid4().hex[:8]
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as client:
        await client.post(
            "/api/v4/users",
            json={"email": "admin@contextos.test", "username": _USERNAME, "password": _PASSWORD},
        )
        response = await client.post(
            "/api/v4/users/login", json={"login_id": _USERNAME, "password": _PASSWORD}
        )
        response.raise_for_status()
        token = response.headers["Token"]
        client.headers["Authorization"] = f"Bearer {token}"

        team = (
            await client.post(
                "/api/v4/teams", json={"name": f"t-{suffix}", "display_name": "Demo", "type": "O"}
            )
        ).json()
        channel = (
            await client.post(
                "/api/v4/channels",
                json={"team_id": team["id"], "name": f"c-{suffix}", "display_name": "ops", "type": "O"},
            )
        ).json()

        for message in ["Deploy to prod completed.", "Error rate spiked briefly post-deploy."]:
            await client.post("/api/v4/posts", json={"channel_id": channel["id"], "message": message})

    return token, channel["id"]


async def main() -> None:
    token, channel_id = await _bootstrap()

    context_os = ContextOS()
    extractor = MattermostExtractor(BASE_URL, channel_id, token=token)
    nodes = await context_os.ingest_source(extractor, tenant_id="acme")

    print(f"ingest_source() pulled {len(nodes)} real Mattermost message(s):")
    for node in nodes:
        print(f"  {node.content}")


if __name__ == "__main__":
    asyncio.run(main())
