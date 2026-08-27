from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from app.goals import GoalEngine, SalesMetrics
from app.pdca_engine import FunnelSnapshot


@dataclass
class DealRecord:
    company_name: str
    stage: str
    proposed_price_yen: Optional[int] = None
    probability_pct: Optional[float] = None
    lost_reason: str = ""


class ExecutiveDashboard:
    """Aggregate observed pipeline data into management metrics.

    Forecasting rules:
    - Expected revenue uses only explicit deal probabilities and proposed prices.
    - Missing probabilities/prices are excluded rather than estimated.
    - Won revenue uses only deals explicitly marked won/closed_won.
    """

    def __init__(self) -> None:
        self.goals = GoalEngine()

    @staticmethod
    def _stage_count(deals: list[DealRecord], stage_names: set[str]) -> int:
        return sum(1 for d in deals if d.stage.lower() in stage_names)

    @staticmethod
    def _expected_revenue(deals: list[DealRecord]) -> int:
        total = 0.0
        for d in deals:
            if d.proposed_price_yen is None or d.probability_pct is None:
                continue
            if d.stage.lower() in {"lost", "closed_lost", "closed", "won", "closed_won"}:
                continue
            total += d.proposed_price_yen * (max(0.0, min(100.0, d.probability_pct)) / 100.0)
        return round(total)

    @staticmethod
    def _won_revenue(deals: list[DealRecord]) -> int:
        return sum(
            int(d.proposed_price_yen or 0)
            for d in deals
            if d.stage.lower() in {"won", "closed_won"}
        )

    @staticmethod
    def _loss_reasons(deals: list[DealRecord]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in deals:
            if d.stage.lower() not in {"lost", "closed_lost"}:
                continue
            reason = d.lost_reason.strip() or "未分類"
            counts[reason] = counts.get(reason, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))

    def build(self, snapshot: FunnelSnapshot, deals: list[DealRecord]) -> dict[str, Any]:
        goal = self.goals.load_or_create()
        goal_eval = self.goals.evaluate(goal, SalesMetrics(**asdict(snapshot)))

        open_pipeline_value = sum(
            int(d.proposed_price_yen or 0)
            for d in deals
            if d.stage.lower() not in {"lost", "closed_lost", "closed", "won", "closed_won"}
        )
        expected_revenue = self._expected_revenue(deals)
        won_revenue = self._won_revenue(deals)

        priorities: list[str] = []
        if snapshot.wins >= goal.target_wins:
            priorities.append("KGI達成済み。受注要因を記録し、再現性の高い営業パターンを標準化する")
        elif snapshot.proposals > snapshot.wins:
            priorities.append("提案済み案件の決裁障壁・価格・次回接触日を優先確認する")
        elif snapshot.meetings > snapshot.proposals:
            priorities.append("商談済み案件を提案化する")
        elif snapshot.replies > snapshot.meetings:
            priorities.append("返信済み案件の商談化を優先する")
        else:
            priorities.append(goal_eval["next_focus"])

        return {
            "goal": goal_eval["goal"],
            "days_remaining": goal_eval["days_remaining"],
            "health": goal_eval["health"],
            "funnel": asdict(snapshot),
            "pipeline": {
                "open_deal_count": sum(1 for d in deals if d.stage.lower() not in {"lost", "closed_lost", "closed", "won", "closed_won"}),
                "open_pipeline_value_yen": open_pipeline_value,
                "expected_revenue_yen": expected_revenue,
                "won_revenue_yen": won_revenue,
                "proposal_count": self._stage_count(deals, {"proposal"}),
                "meeting_count": self._stage_count(deals, {"meeting"}),
                "won_count": self._stage_count(deals, {"won", "closed_won"}),
                "lost_count": self._stage_count(deals, {"lost", "closed_lost"}),
            },
            "loss_reasons": self._loss_reasons(deals),
            "management_priorities": priorities,
            "forecast_rule": "期待売上は、明示された提案価格×明示された案件確率のみで計算。欠損値は推定しない。",
        }
