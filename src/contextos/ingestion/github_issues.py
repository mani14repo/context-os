from __future__ import annotations

from typing import Any

import httpx

from contextos.models import Classification, ContextNode, MemoryType

__all__ = ["GitHubIssuesExtractor"]


class GitHubIssuesExtractor:
    """Fetches issues from a GitHub repository via the public REST API and maps
    each one to a ContextNode. Works unauthenticated against public repositories
    (subject to GitHub's unauthenticated rate limit); pass `token` for private
    repos or a higher rate limit. Requires `pip install -e ".[http]"` (reuses
    httpx, no GitHub-specific SDK).

    GitHub's `/issues` endpoint also returns pull requests (a PR is a kind of
    issue in GitHub's data model) -- these are filtered out so only genuine issues
    become ContextNodes.
    """

    def __init__(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "open",
        labels: str | None = None,
        max_results: int = 30,
        token: str | None = None,
        node_type: str = "github_issue",
        memory_type: MemoryType = MemoryType.OPERATIONAL,
        classification: Classification = Classification.INTERNAL,
        importance: float = 0.5,
        base_url: str = "https://api.github.com",
        timeout: float = 10.0,
    ) -> None:
        self._owner = owner
        self._repo = repo
        self._state = state
        self._labels = labels
        self._max_results = max_results
        self._token = token
        self._node_type = node_type
        self._memory_type = memory_type
        self._classification = classification
        self._importance = importance
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _to_node(self, tenant_id: str, issue: dict[str, Any]) -> ContextNode:
        labels = [
            label["name"] if isinstance(label, dict) else label
            for label in issue.get("labels", [])
        ]
        return ContextNode(
            tenant_id=tenant_id,
            node_type=self._node_type,
            memory_type=self._memory_type,
            classification=self._classification,
            title=issue.get("title"),
            content=issue.get("body") or "",
            importance=self._importance,
            metadata={
                "source_type": "github_issue",
                "source_id": issue["number"],
                "source_url": issue.get("html_url"),
                "state": issue.get("state"),
                "labels": labels,
            },
        )

    async def extract(self, *, tenant_id: str) -> list[ContextNode]:
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        params: dict[str, Any] = {"state": self._state, "per_page": min(self._max_results, 100)}
        if self._labels:
            params["labels"] = self._labels

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/repos/{self._owner}/{self._repo}/issues",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            issues = response.json()

        nodes = [
            self._to_node(tenant_id, issue)
            for issue in issues
            if "pull_request" not in issue
        ]
        return nodes[: self._max_results]
