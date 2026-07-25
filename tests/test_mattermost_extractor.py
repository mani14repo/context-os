import os
import uuid
from collections.abc import AsyncIterator

import pytest

pytest.importorskip("httpx")

import httpx

from contextos.ingestion.mattermost import MattermostExtractor

_BASE_URL = os.environ.get("CONTEXTOS_TEST_MATTERMOST_URL")
_ADMIN_EMAIL = "admin@contextos.test"
_ADMIN_USERNAME = "ctxadmin"
_ADMIN_PASSWORD = "ContextOS-Test-123!"

pytestmark = pytest.mark.skipif(
    not _BASE_URL, reason="CONTEXTOS_TEST_MATTERMOST_URL not set -- skipping live Mattermost tests"
)


async def _admin_token() -> str:
    """Bootstraps (or reuses) a single admin account on the live Mattermost server.
    The very first user registered on a fresh instance always becomes system admin
    regardless of the open-registration setting -- later signups don't, so every
    test reuses this one account rather than trying to self-register per test."""
    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=15) as client:
        await client.post(
            "/api/v4/users",
            json={"email": _ADMIN_EMAIL, "username": _ADMIN_USERNAME, "password": _ADMIN_PASSWORD},
        )
        response = await client.post(
            "/api/v4/users/login", json={"login_id": _ADMIN_USERNAME, "password": _ADMIN_PASSWORD}
        )
        response.raise_for_status()
        token = response.headers["Token"]
        return token


async def _create_channel_with_posts(token: str, messages: list[str]) -> str:
    """Creates a fresh team + channel and posts `messages` into it, returning the
    channel id. Each test gets its own team/channel so tests don't interfere."""
    suffix = uuid.uuid4().hex[:12]
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=_BASE_URL, headers=headers, timeout=15) as client:
        team_response = await client.post(
            "/api/v4/teams", json={"name": f"t-{suffix}", "display_name": "ContextOS test", "type": "O"}
        )
        team_response.raise_for_status()
        team_id = team_response.json()["id"]

        channel_response = await client.post(
            "/api/v4/channels",
            json={"team_id": team_id, "name": f"c-{suffix}", "display_name": "ops", "type": "O"},
        )
        channel_response.raise_for_status()
        channel_id: str = channel_response.json()["id"]

        for message in messages:
            post_response = await client.post(
                "/api/v4/posts", json={"channel_id": channel_id, "message": message}
            )
            post_response.raise_for_status()
    return channel_id


@pytest.fixture(scope="module")
async def token() -> str:
    return await _admin_token()


@pytest.fixture
async def channel_with_two_messages(token: str) -> AsyncIterator[str]:
    channel_id = await _create_channel_with_posts(
        token, ["Deploy to prod completed.", "Error rate spiked briefly post-deploy."]
    )
    yield channel_id


@pytest.mark.asyncio
async def test_extracts_real_posts_from_a_channel(token: str, channel_with_two_messages: str) -> None:
    extractor = MattermostExtractor(_BASE_URL, channel_with_two_messages, token=token)

    nodes = await extractor.extract(tenant_id="t1")

    assert len(nodes) == 2
    # order should be chronological (oldest first) -- the deploy message was posted first
    assert nodes[0].content == "Deploy to prod completed."
    assert nodes[1].content == "Error rate spiked briefly post-deploy."
    assert all(node.metadata["source_type"] == "chat_message" for node in nodes)
    assert all(node.metadata["channel_id"] == channel_with_two_messages for node in nodes)


@pytest.mark.asyncio
async def test_system_join_message_is_filtered_out(token: str) -> None:
    # _create_channel_with_posts always generates a "<admin> joined the channel"
    # system post as a side effect of creating the channel -- only the two
    # explicit user messages should survive into ContextNodes.
    channel_id = await _create_channel_with_posts(token, ["Just one real message."])

    nodes = await MattermostExtractor(_BASE_URL, channel_id, token=token).extract(tenant_id="t1")

    assert len(nodes) == 1
    assert nodes[0].content == "Just one real message."


@pytest.mark.asyncio
async def test_max_messages_caps_results(token: str) -> None:
    channel_id = await _create_channel_with_posts(token, [f"message {i}" for i in range(5)])

    nodes = await MattermostExtractor(
        _BASE_URL, channel_id, token=token, max_messages=2
    ).extract(tenant_id="t1")

    assert len(nodes) == 2


@pytest.mark.asyncio
async def test_invalid_token_raises_http_status_error(channel_with_two_messages: str) -> None:
    extractor = MattermostExtractor(_BASE_URL, channel_with_two_messages, token="not-a-real-token")
    with pytest.raises(httpx.HTTPStatusError):
        await extractor.extract(tenant_id="t1")


@pytest.mark.asyncio
async def test_ingest_source_persists_mattermost_messages(
    token: str, channel_with_two_messages: str
) -> None:
    from contextos import ContextOS

    context_os = ContextOS()
    extractor = MattermostExtractor(_BASE_URL, channel_with_two_messages, token=token)
    nodes = await context_os.ingest_source(extractor, tenant_id="t1")

    assert len(nodes) == 2
    for node in nodes:
        stored = await context_os.store.get_node("t1", node.id)
        assert stored is not None
