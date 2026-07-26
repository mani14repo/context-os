"""Integrating an existing ML model (XGBoost) with ContextOS.

Requires `pip install -e ".[ml]"`.

ContextOS doesn't train or run models -- it's a context/memory layer that sits
next to whatever ML pipeline you already have. This example shows the seam:
train an ordinary XGBoost classifier on synthetic credit-card transactions
(essential vs. discretionary spend), capture each prediction *and* its
per-feature contribution (XGBoost's built-in pred_contribs -- SHAP-style
explainability with no separate `shap` dependency) as a governed ContextNode,
then use ContextOS.assemble() to retrieve the most relevant discretionary-spend
insights for a savings task -- plus a provenance manifest on the top insight,
since "why did the model flag this" is exactly the kind of decision that
benefits from a tamper-evident audit trail.
"""

import asyncio
import random

import numpy as np
import xgboost as xgb

from contextos import Classification, ContextNode, ContextOS, ContextRequest, MemoryType
from contextos.provenance import build_provenance_manifest

_CATEGORIES = ["groceries", "dining", "subscriptions", "travel", "entertainment", "utilities", "shopping"]
_ESSENTIAL = {"groceries", "utilities"}
_MERCHANTS = {
    "groceries": ["Trader Joe's", "Whole Foods", "Kroger"],
    "dining": ["Blue Bottle Coffee", "Chipotle", "Olive Garden"],
    "subscriptions": ["Netflix", "Spotify", "Adobe Creative Cloud"],
    "travel": ["Delta Air Lines", "Marriott", "Uber"],
    "entertainment": ["AMC Theatres", "Steam", "Ticketmaster"],
    "utilities": ["City Power & Light", "Comcast Internet", "Water Utility"],
    "shopping": ["Amazon", "Target", "Best Buy"],
}
_FEATURE_NAMES = ["category_id", "amount", "day_of_month", "is_recurring"]


def _print_spending_summary(transactions: list[dict[str, object]]) -> None:
    """Baseline spending behavior across the full transaction set, independent of
    the model -- so the model-flagged insights below read as a drill-down against a
    known total, not floating numbers with nothing to compare them to."""
    total = sum(float(t["amount"]) for t in transactions)  # type: ignore[arg-type]
    essential_total = sum(float(t["amount"]) for t in transactions if t["category"] in _ESSENTIAL)  # type: ignore[arg-type]
    by_category: dict[str, float] = {}
    for t in transactions:
        category = str(t["category"])
        by_category[category] = by_category.get(category, 0.0) + float(t["amount"])  # type: ignore[arg-type]

    print(f"Current spending behavior ({len(transactions)} transactions, full period):")
    print(f"  Total spend:    ${total:,.2f}")
    print(f"  Essential:      ${essential_total:,.2f}  (groceries, utilities)")
    print(f"  Discretionary:  ${total - essential_total:,.2f}  (everything else)")
    print("\n  By category:")
    for category, amount in sorted(by_category.items(), key=lambda kv: kv[1], reverse=True):
        print(f"    {category:<14} ${amount:,.2f}")
    print()


def _generate_transactions(n: int, *, seed: int = 42) -> list[dict[str, object]]:
    """Synthetic transactions with a noisy-but-learnable essential/discretionary label."""
    rng = random.Random(seed)
    transactions = []
    for _ in range(n):
        category = rng.choice(_CATEGORIES)
        merchant = rng.choice(_MERCHANTS[category])
        amount = round(rng.uniform(4, 30) if category in _ESSENTIAL else rng.uniform(8, 220), 2)
        day_of_month = rng.randint(1, 28)
        is_recurring = category in {"subscriptions", "utilities"} or rng.random() < 0.1
        label = 0.0 if category in _ESSENTIAL else 1.0
        # A handful of large "essential" purchases and small "discretionary" ones flip
        # label, so the model has to learn from amount too, not just memorize category.
        if rng.random() < 0.12:
            label = 1.0 - label
        transactions.append(
            {
                "category": category,
                "merchant": merchant,
                "amount": amount,
                "day_of_month": day_of_month,
                "is_recurring": is_recurring,
                "label": label,
            }
        )
    return transactions


def _features(transaction: dict[str, object]) -> list[float]:
    return [
        float(_CATEGORIES.index(str(transaction["category"]))),
        float(transaction["amount"]),  # type: ignore[arg-type]
        float(transaction["day_of_month"]),  # type: ignore[arg-type]
        1.0 if transaction["is_recurring"] else 0.0,
    ]


async def main() -> None:
    transactions = _generate_transactions(240)
    _print_spending_summary(transactions)

    features = np.array([_features(t) for t in transactions])
    labels = np.array([t["label"] for t in transactions])

    dtrain = xgb.DMatrix(features, label=labels, feature_names=_FEATURE_NAMES)
    booster = xgb.train(
        {"objective": "binary:logistic", "max_depth": 3, "eta": 0.3, "eval_metric": "logloss"},
        dtrain,
        num_boost_round=30,
    )

    probabilities = booster.predict(dtrain)
    # pred_contribs gives per-feature, per-prediction additive contributions (the last
    # column is the bias term) -- XGBoost's built-in SHAP-style explainability.
    contributions = booster.predict(dtrain, pred_contribs=True)

    context_os = ContextOS()
    insight_ids = []
    for transaction, probability, contribution in zip(transactions, probabilities, contributions, strict=True):
        if probability < 0.6:
            continue  # only surface confident discretionary calls as context
        top_feature_index = int(np.argmax(np.abs(contribution[:-1])))
        top_feature = _FEATURE_NAMES[top_feature_index]
        node = await context_os.ingest(
            ContextNode(
                tenant_id="demo",
                node_type="spend_insight",
                memory_type=MemoryType.EPISODIC,
                classification=Classification.CONFIDENTIAL,
                title=f"{transaction['merchant']} (${transaction['amount']:.2f})",
                content=(
                    f"${transaction['amount']:.2f} at {transaction['merchant']} ({transaction['category']}) "
                    f"on day {transaction['day_of_month']} of the month. XGBoost model flags this as "
                    f"discretionary spending (confidence {probability:.2f}), driven mainly by "
                    f"{top_feature} (contribution {contribution[top_feature_index]:+.3f})."
                ),
                importance=float(probability),
                metadata={
                    "category": transaction["category"],
                    "amount": transaction["amount"],
                    "model_probability": float(probability),
                    "top_feature": top_feature,
                },
            )
        )
        insight_ids.append(node.id)

    print(
        f"Ingested {len(insight_ids)} model-flagged discretionary-spend insights "
        f"out of {len(transactions)} transactions.\n"
    )

    package = await context_os.assemble(
        ContextRequest(
            tenant_id="demo",
            task="Where can I cut monthly spending?",
            agent="savings-advisor",
            memory_scopes={MemoryType.EPISODIC},
            token_budget=800,
        )
    )
    print(f"assemble() surfaced {len(package.items)} relevant insight(s):")
    by_category: dict[str, float] = {}
    for item in package.items:
        print(f"  - {item.node.title}: score={item.score}")
        category = str(item.node.metadata.get("category", "unknown"))
        by_category[category] = by_category.get(category, 0.0) + float(item.node.metadata.get("amount", 0.0))

    if by_category:
        print("\nPotential monthly savings by category (from retrieved context only):")
        for category, total in sorted(by_category.items(), key=lambda kv: kv[1], reverse=True):
            print(f"  - {category}: ${total:.2f}")

    if package.items:
        top_insight_id = package.items[0].node.id
        manifest = await build_provenance_manifest(context_os, "demo", top_insight_id)
        print(
            f"\nProvenance manifest for the top insight: {len(manifest.entries)} version(s), "
            f"hash={manifest.manifest_hash[:16]}... -- an auditable record of how this "
            f"model-driven recommendation came to be."
        )


if __name__ == "__main__":
    asyncio.run(main())
