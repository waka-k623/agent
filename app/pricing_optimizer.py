from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class PricingEvidence:
    company_name: str
    delivery_cost_yen: Optional[int] = None
    estimated_hours: Optional[float] = None
    hourly_cost_yen: Optional[int] = None
    customer_budget_min_yen: Optional[int] = None
    customer_budget_max_yen: Optional[int] = None
    verified_competitor_prices_yen: Optional[list[int]] = None
    historical_won_prices_yen: Optional[list[int]] = None
    historical_lost_prices_yen: Optional[list[int]] = None


@dataclass
class PricingRecommendation:
    status: str
    company_name: str
    floor_price_yen: Optional[int]
    recommended_price_yen: Optional[int]
    ceiling_price_yen: Optional[int]
    gross_margin_pct: Optional[float]
    rationale: list[str]
    missing_evidence: list[str]
    approval_required: bool = True


class PricingOptimizer:
    """Produces a price only from observed cost/budget/market/history evidence.

    It never fabricates willingness-to-pay, competitor prices, or conversion assumptions.
    Final customer-facing pricing remains human approval gated.
    """

    def recommend(self, e: PricingEvidence) -> PricingRecommendation:
        missing: list[str] = []
        cost = e.delivery_cost_yen
        if cost is None and e.estimated_hours is not None and e.hourly_cost_yen is not None:
            cost = round(e.estimated_hours * e.hourly_cost_yen)
        if cost is None:
            missing.append("delivery_cost_yen または estimated_hours + hourly_cost_yen")

        budget_known = e.customer_budget_min_yen is not None or e.customer_budget_max_yen is not None
        market = [x for x in (e.verified_competitor_prices_yen or []) if isinstance(x, int) and x > 0]
        won = [x for x in (e.historical_won_prices_yen or []) if isinstance(x, int) and x > 0]
        lost = [x for x in (e.historical_lost_prices_yen or []) if isinstance(x, int) and x > 0]

        if not budget_known and not market and not won:
            missing.append("顧客予算・検証済み競合価格・過去受注価格のいずれか")

        if cost is None or (not budget_known and not market and not won):
            return PricingRecommendation(
                status="RESEARCH",
                company_name=e.company_name,
                floor_price_yen=cost,
                recommended_price_yen=None,
                ceiling_price_yen=e.customer_budget_max_yen,
                gross_margin_pct=None,
                rationale=["価格を推測せず、必要な実データが揃うまで提案価格を生成しない。"],
                missing_evidence=missing,
            )

        anchors: list[int] = []
        rationale: list[str] = [f"確認済み原価下限: ¥{cost:,}"]
        if e.customer_budget_min_yen:
            anchors.append(e.customer_budget_min_yen)
            rationale.append(f"顧客予算下限: ¥{e.customer_budget_min_yen:,}")
        if e.customer_budget_max_yen:
            anchors.append(e.customer_budget_max_yen)
            rationale.append(f"顧客予算上限: ¥{e.customer_budget_max_yen:,}")
        if market:
            median_market = sorted(market)[len(market) // 2]
            anchors.append(median_market)
            rationale.append(f"検証済み競合価格中央値: ¥{median_market:,}")
        if won:
            median_won = sorted(won)[len(won) // 2]
            anchors.append(median_won)
            rationale.append(f"過去受注価格中央値: ¥{median_won:,}")

        # Median of factual anchors is used as a neutral starting point; never below known delivery cost.
        recommended = max(cost, sorted(anchors)[len(anchors) // 2]) if anchors else cost
        if e.customer_budget_max_yen is not None:
            recommended = min(recommended, e.customer_budget_max_yen)

        # If budget ceiling is below delivery cost, do not recommend a loss-making deal.
        if recommended < cost or (e.customer_budget_max_yen is not None and e.customer_budget_max_yen < cost):
            return PricingRecommendation(
                status="NO_GO",
                company_name=e.company_name,
                floor_price_yen=cost,
                recommended_price_yen=None,
                ceiling_price_yen=e.customer_budget_max_yen,
                gross_margin_pct=None,
                rationale=rationale + ["確認済み顧客予算上限が原価を下回るため、現条件では提案しない。"],
                missing_evidence=[],
            )

        margin = round(((recommended - cost) / recommended) * 100, 1) if recommended > 0 else None
        if lost:
            rationale.append(f"過去失注価格データ {len(lost)}件を保持。因果関係を断定せず参考情報として使用。")

        return PricingRecommendation(
            status="READY_FOR_APPROVAL",
            company_name=e.company_name,
            floor_price_yen=cost,
            recommended_price_yen=recommended,
            ceiling_price_yen=e.customer_budget_max_yen,
            gross_margin_pct=margin,
            rationale=rationale,
            missing_evidence=[],
        )


def to_dict(result: PricingRecommendation) -> dict:
    return asdict(result)
