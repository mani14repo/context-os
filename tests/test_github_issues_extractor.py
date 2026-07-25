import httpx
import pytest

pytest.importorskip("httpx")

from contextos.ingestion.github_issues import GitHubIssuesExtractor

# octocat/Hello-World is GitHub's own long-standing demo repository, used across
# their docs specifically as a stable target for API examples -- it reliably has a
# mix of real issues (people testing the API against it) and pull requests, which
# is exactly what these tests need to exercise the PR-filtering behavior.
_OWNER = "octocat"
_REPO = "Hello-World"


@pytest.mark.asyncio
async def test_extracts_real_issues_from_a_public_repo() -> None:
    nodes = await GitHubIssuesExtractor(_OWNER, _REPO, state="all", max_results=10).extract(
        tenant_id="t1"
    )

    assert len(nodes) > 0
    for node in nodes:
        assert node.tenant_id == "t1"
        assert node.node_type == "github_issue"
        assert node.title
        assert node.metadata["source_type"] == "github_issue"
        assert isinstance(node.metadata["source_id"], int)
        assert node.metadata["source_url"].startswith(
            f"https://github.com/{_OWNER}/{_REPO}/issues/"
        )


@pytest.mark.asyncio
async def test_pull_requests_are_filtered_out() -> None:
    nodes = await GitHubIssuesExtractor(_OWNER, _REPO, state="all", max_results=30).extract(
        tenant_id="t1"
    )

    # GitHub's /issues endpoint returns PRs too; every returned node must be a real
    # issue -- there is no reliable field on our ContextNode to check this from the
    # outside, so the meaningful assertion is indirect: every source_url points at
    # /issues/, never /pull/.
    for node in nodes:
        assert "/issues/" in node.metadata["source_url"]
        assert "/pull/" not in node.metadata["source_url"]


@pytest.mark.asyncio
async def test_max_results_caps_the_returned_nodes() -> None:
    nodes = await GitHubIssuesExtractor(_OWNER, _REPO, state="all", max_results=3).extract(
        tenant_id="t1"
    )

    assert len(nodes) <= 3


@pytest.mark.asyncio
async def test_nonexistent_repo_raises_http_status_error() -> None:
    extractor = GitHubIssuesExtractor("this-owner-does-not-exist-abcxyz", "nope-repo-xyz")
    with pytest.raises(httpx.HTTPStatusError):
        await extractor.extract(tenant_id="t1")


@pytest.mark.asyncio
async def test_ingest_source_persists_github_issues() -> None:
    from contextos import ContextOS

    context_os = ContextOS()
    extractor = GitHubIssuesExtractor(_OWNER, _REPO, state="all", max_results=2)
    nodes = await context_os.ingest_source(extractor, tenant_id="t1")

    assert len(nodes) > 0
    for node in nodes:
        stored = await context_os.store.get_node("t1", node.id)
        assert stored is not None
