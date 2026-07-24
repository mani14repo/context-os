import uuid

import pytest

from contextos import ContextNode, ContextOS, MemoryType
from contextos.evaluation import EvalCase, run_eval_suite


@pytest.mark.asyncio
async def test_perfect_match_scores_1_0() -> None:
    context_os = ContextOS()
    node = await context_os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            content="Kubernetes cluster upgrades require draining nodes first.",
            importance=0.8,
        )
    )
    report = await run_eval_suite(
        context_os,
        [
            EvalCase(
                case_id="c1",
                tenant_id="t1",
                task="Kubernetes cluster upgrade",
                expected_node_ids={node.id},
            )
        ],
    )
    result = report.results[0]
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0
    assert result.missing_expected == []


@pytest.mark.asyncio
async def test_partial_match_scores_hand_computed_values() -> None:
    context_os = ContextOS()
    expected_node = await context_os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            title="Kubernetes upgrade checklist",
            content="Kubernetes cluster upgrades require draining nodes first.",
            importance=0.8,
        )
    )
    await context_os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            title="Kubernetes networking",
            content="Kubernetes services route traffic to matching pod labels.",
            importance=0.8,
        )
    )
    # Both nodes are lexically related to "Kubernetes cluster" and fit a generous
    # budget, but the eval case only considers the first one correct -- one of the
    # two returned nodes is a false positive by construction.
    report = await run_eval_suite(
        context_os,
        [
            EvalCase(
                case_id="c1",
                tenant_id="t1",
                task="Kubernetes cluster upgrade",
                expected_node_ids={expected_node.id},
                token_budget=2000,
            )
        ],
    )
    result = report.results[0]
    assert len(result.returned_node_ids) == 2
    assert result.precision == 0.5  # 1 true positive / 2 returned
    assert result.recall == 1.0  # 1 true positive / 1 expected
    assert result.f1 == pytest.approx(0.6667, abs=1e-4)


@pytest.mark.asyncio
async def test_nothing_expected_and_nothing_returned_is_perfect() -> None:
    context_os = ContextOS()
    await context_os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            content="Kubernetes cluster upgrades require draining nodes first.",
            importance=0.0,
        )
    )
    report = await run_eval_suite(
        context_os,
        [
            EvalCase(
                case_id="c1",
                tenant_id="t1",
                task="completely unrelated coffee brewing techniques",
                expected_node_ids=set(),
            )
        ],
    )
    result = report.results[0]
    assert result.returned_node_ids == []
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0


@pytest.mark.asyncio
async def test_unexpected_hit_is_a_false_positive() -> None:
    context_os = ContextOS()
    node = await context_os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            content="Kubernetes cluster upgrades require draining nodes first.",
            importance=0.8,
        )
    )
    report = await run_eval_suite(
        context_os,
        [
            EvalCase(
                case_id="c1",
                tenant_id="t1",
                task="Kubernetes cluster upgrade",
                expected_node_ids=set(),  # ground truth says nothing should match
            )
        ],
    )
    result = report.results[0]
    assert result.returned_node_ids == [node.id]
    assert result.precision == 0.0
    assert result.recall == 1.0
    assert result.f1 == 0.0


@pytest.mark.asyncio
async def test_total_miss_scores_0_recall() -> None:
    context_os = ContextOS()
    report = await run_eval_suite(
        context_os,
        [
            EvalCase(
                case_id="c1",
                tenant_id="t1",
                task="anything",
                expected_node_ids={uuid.uuid4()},
            )
        ],
    )
    result = report.results[0]
    assert result.returned_node_ids == []
    assert result.precision == 1.0
    assert result.recall == 0.0
    assert result.f1 == 0.0


@pytest.mark.asyncio
async def test_report_aggregates_mean_across_cases() -> None:
    context_os = ContextOS()
    node = await context_os.ingest(
        ContextNode(
            tenant_id="t1",
            node_type="fact",
            memory_type=MemoryType.SEMANTIC,
            content="Kubernetes cluster upgrades require draining nodes first.",
            importance=0.8,
        )
    )
    report = await run_eval_suite(
        context_os,
        [
            EvalCase(
                case_id="perfect",
                tenant_id="t1",
                task="Kubernetes cluster upgrade",
                expected_node_ids={node.id},
            ),
            # A different, empty tenant -- nothing ingested there, so this is a real
            # total miss rather than accidentally matching t1's node via the
            # importance floor in score_node() (importance alone can clear the
            # relevance threshold even with zero lexical overlap).
            EvalCase(
                case_id="total-miss",
                tenant_id="t2",
                task="anything",
                expected_node_ids={uuid.uuid4()},
            ),
        ],
    )
    assert len(report.results) == 2
    assert report.results[1].returned_node_ids == []
    assert report.mean_precision == pytest.approx((1.0 + 1.0) / 2)
    assert report.mean_recall == pytest.approx((1.0 + 0.0) / 2)
    assert report.mean_f1 == pytest.approx((1.0 + 0.0) / 2)
    assert report.mean_latency_seconds >= 0.0
