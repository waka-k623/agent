from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class FollowupQueueBridge:
    """Persist follow-up actions into the same approval workflow without auto-sending."""

    def __init__(self, queue_path: Path | None = None) -> None:
        self.queue_path = queue_path or Path("data/outreach_approval_queue.json")

    def _load(self) -> list[dict[str, Any]]:
        if not self.queue_path.exists():
            return []
        try:
            raw = json.loads(self.queue_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            for key in ("items", "records", "results"):
                if isinstance(raw.get(key), list):
                    return raw[key]
        return []

    def _save(self, rows: list[dict[str, Any]]) -> None:
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        self.queue_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _dedupe_key(company_name: str, action_type: str, followup_number: int = 0) -> str:
        return f"{company_name.strip().lower()}::{action_type}::{followup_number}"

    def apply_decision(self, decision: dict[str, Any]) -> dict[str, Any] | None:
        action = str(decision.get("action") or "")
        company_name = str(decision.get("company_name") or "").strip()
        if not company_name:
            return None

        rows = self._load()
        if action == "prepare_followup":
            message = str(decision.get("followup_message") or "").strip()
            if not message:
                return None
            followup_number = int(decision.get("followup_number") or 0)
            key = self._dedupe_key(company_name, "followup", followup_number)
            if any(str(r.get("dedupe_key") or "") == key for r in rows):
                return None
            item = {
                "id": f"followup-{company_name}-{followup_number}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "dedupe_key": key,
                "company_name": company_name,
                "priority": decision.get("priority", ""),
                "action_type": "followup",
                "status": "pending_approval",
                "message": message,
                "reason": decision.get("reason", ""),
                "reply_summary": decision.get("reply_summary", ""),
                "followup_number": followup_number,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
            rows.append(item)
            self._save(rows)
            return item

        if action == "prepare_meeting":
            key = self._dedupe_key(company_name, "meeting")
            if any(str(r.get("dedupe_key") or "") == key for r in rows):
                return None
            item = {
                "id": f"meeting-{company_name}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "dedupe_key": key,
                "company_name": company_name,
                "priority": decision.get("priority", ""),
                "action_type": "meeting_prepare",
                "status": "pending_approval",
                "reason": decision.get("reason", "商談意向を検知"),
                "reply_summary": decision.get("reply_summary", ""),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
            rows.append(item)
            self._save(rows)
            return item

        return None

    def apply_many(self, decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        added: list[dict[str, Any]] = []
        for decision in decisions:
            item = self.apply_decision(decision)
            if item:
                added.append(item)
        return added
