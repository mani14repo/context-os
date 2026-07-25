"""Ingesting real GitHub issues into ContextOS.

Needs `pip install -e ".[http]"`.

`GitHubIssuesExtractor` hits the real public GitHub REST API -- no local server,
no mock, an actual `octocat/Hello-World` (GitHub's own long-standing demo repo)
issue list. GitHub's `/issues` endpoint also returns pull requests; the extractor
filters those out so every returned node is a genuine issue. Pass `token=...` for
private repositories or a higher rate limit.
"""

import asyncio

from contextos import ContextOS
from contextos.ingestion.github_issues import GitHubIssuesExtractor


async def main() -> None:
    context_os = ContextOS()
    extractor = GitHubIssuesExtractor("octocat", "Hello-World", state="all", max_results=5)
    nodes = await context_os.ingest_source(extractor, tenant_id="acme")

    print(f"ingest_source() pulled {len(nodes)} real issue(s) from octocat/Hello-World:")
    for node in nodes:
        labels = node.metadata["labels"] or "no labels"
        print(f"  #{node.metadata['source_id']} [{node.metadata['state']}] {node.title} ({labels})")


if __name__ == "__main__":
    asyncio.run(main())
