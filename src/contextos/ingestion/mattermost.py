from __future__ import annotations

from typing import Any

import httpx

from contextos.models import Classification, ContextNode, MemoryType

__all__ = ["MattermostExtractor"]


class MattermostExtractor:
    """Fetches recent messages from a Mattermost channel via the REST API and maps
    each post to a ContextNode. Requires `pip install -e ".[mattermost]"` (httpx,
    no Mattermost-specific SDK -- its REST API is simple enough not to need one).

    Mattermost, not a proprietary SaaS chat product, is the "chats/messages"
    connector here specifically because it's self-hostable: it can be run in
    Docker and tested against a real live server the same way every other
    connector in this package is, rather than requiring a hosted account and
    workspace-specific credentials just to run the test suite.

    System messages (joins, leaves, channel renames -- anything with a non-empty
    `type` in Mattermost's post schema) are filtered out; only genuine user
    messages become ContextNodes.
    """

    def __init__(
        self,
        base_url: str,
        channel_id: str,
        *,
        token: str,
        max_messages: int = 100,
        node_type: str = "chat_message",
        memory_type: MemoryType = MemoryType.EPISODIC,
        classification: Classification = Classification.INTERNAL,
        importance: float = 0.5,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._channel_id = channel_id
        self._token = token
        self._max_messages = max_messages
        self._node_type = node_type
        self._memory_type = memory_type
        self._classification = classification
        self._importance = importance
        self._timeout = timeout

    def _to_node(self, tenant_id: str, post: dict[str, Any]) -> ContextNode:
        return ContextNode(
            tenant_id=tenant_id,
            node_type=self._node_type,
            memory_type=self._memory_type,
            classification=self._classification,
            content=post["message"],
            importance=self._importance,
            metadata={
                "source_type": "chat_message",
                "source_id": post["id"],
                "channel_id": post["channel_id"],
                "user_id": post.get("user_id"),
                "created_at_ms": post.get("create_at"),
            },
        )

    async def extract(self, *, tenant_id: str) -> list[ContextNode]:
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(
            base_url=self._base_url, headers=headers, timeout=self._timeout
        ) as client:
            response = await client.get(
                f"/api/v4/channels/{self._channel_id}/posts",
                params={"per_page": min(self._max_messages, 200)},
            )
            response.raise_for_status()
            payload = response.json()

        posts = payload.get("posts", {})
        # Mattermost returns `order` newest-first; reverse for chronological reading order.
        order = list(reversed(payload.get("order", [])))[: self._max_messages]
        nodes = []
        for post_id in order:
            post = posts[post_id]
            if not post.get("message") or post.get("type"):
                continue
            nodes.append(self._to_node(tenant_id, post))
        return nodes
