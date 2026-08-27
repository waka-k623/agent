from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.outreach_planner import OutreachPlanner


class PromotionEngine:
    """Promote only verified P0/P1 prospects into the outreach approval queue.

    P2/RESEARCH/DROP never enter the queue. Existing queue entries are deduplicated
    by company name + contact target to avoid repeated outreach proposals.
    """

    def __init__(self, company_id: str = "default", queue_path: str = "data/outreach_approval_queue.json") -> None:
        self.planner = OutreachPlanner(company_id=company_id)
        self.queue_path = Path(queue_path)

    def _load_queue(self) -> list[dict[str, Any]]:
        if not self.queue_path.exists():
            return []
        try:
            data = json.loads(self.queue_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("items", "records", "results"):
                if isinstance(data.get(key), list):
                    return data[key]
        return []

    def _save_queue(self, queue: list[dict[str, Any]]) -> None:
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        self.queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _priority(item: dict[str, Any]) -> str:
        score = item.get("score") or {}
        return str(score.get("priority") or item.get("priority") or "")

    def promote(self, scored_items: list[dict[str, Any]]) -> dict[str, Any]:
        eligible = [item for item in scored_items if self._priority(item) in {"P0", "P1"}]
        plans = self.planner.plan_batch(eligible)

        queue = self._load_queue()
        existing_keys = {
            (str(x.get("company_name") or "").strip(), str(x.get("contact_target") or "").strip())
            for x in queue
        }

        promoted: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for plan in plans:
            if plan.get("status") != "ready_for_approval":
                blocked.append(plan)
                continue
            key = (str(plan.get("company_name") or "").strip(), str(plan.get("contact_target") or "").strip())
            if key in existing_keys:
                continue
            queue.append(plan)
            existing_keys.add(key)
            promoted.append(plan)

        self._save_queue(queue)
        return {
            "eligible_count": len(eligible),
            "promoted_count": len(promoted),
            "blocked_count": len(blocked),
            "promoted": promoted,
            "blocked": blocked,
            "queue_size": len(queue),
        }
