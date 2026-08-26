from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.actions.planner import ActionPlanner
from app.orchestrator import SalesAgentOrchestrator


class SalesReviewQueue:
    """Build a human-review queue from integrated Sales Agent analysis."""

    def __init__(self, company_id: str = "default") -> None:
        self.agent = SalesAgentOrchestrator(company_id=company_id)
        self.planner = ActionPlanner()

    def build(self, max_results: int = 10) -> list[dict[str, Any]]:
        analyses = self.agent.analyze_inbox(max_results=max_results)
        queue: list[dict[str, Any]] = []

        for analysis in analyses:
            actions = self.planner.plan(analysis)
            queue.append(
                {
                    "analysis": analysis,
                    "proposed_actions": [asdict(action) for action in actions],
                }
            )

        return queue
