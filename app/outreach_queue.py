from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class OutreachQueueStore:
    QUEUE_PATH = Path("data/outreach_approval_queue.json")
    DECISIONS_PATH = Path("data/outreach_decisions.json")

    def load_queue(self) -> list[dict[str, Any]]:
        if not self.QUEUE_PATH.exists():
            return []
        data = json.loads(self.QUEUE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []

    def load_decisions(self) -> dict[str, dict[str, Any]]:
        if not self.DECISIONS_PATH.exists():
            return {}
        data = json.loads(self.DECISIONS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    @staticmethod
    def key(plan: dict[str, Any]) -> str:
        return f"{plan.get('company_name','')}::{plan.get('channel','')}::{plan.get('contact_target','')}"

    def save_decision(self, plan: dict[str, Any], status: str, actor: str = "demo") -> None:
        decisions = self.load_decisions()
        decisions[self.key(plan)] = {
            "status": status,
            "actor": actor,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "company_name": plan.get("company_name", ""),
            "priority": plan.get("priority", ""),
            "channel": plan.get("channel", ""),
            "contact_target": plan.get("contact_target", ""),
        }
        self.DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.DECISIONS_PATH.write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
