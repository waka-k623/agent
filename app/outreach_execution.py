from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any
import json

from app.actions.approval import ProposedAction
from app.actions.executor import ActionExecutor


@dataclass
class OutreachTimer:
    company_name: str
    priority: str
    first_contact_date: str
    last_contact_date: str
    reply_deadline_date: str
    followup_count: int = 0
    status: str = "awaiting_reply"
    channel: str = "email"
    contact_target: str = ""


class OutreachExecutionManager:
    """Turn approved email outreach into a Gmail draft and start the reply timer.

    Rules:
    - Only queue items already marked approved are eligible.
    - The actual Gmail draft is created only through ActionExecutor, which enforces
      explicit action approval and live-write enablement.
    - Creating a draft does not imply the email was sent.
    - The response timer starts when the draft action is executed and the outreach
      is marked as ready/sent by the surrounding workflow.
    """

    DATA_DIR = Path("data")
    TIMER_PATH = DATA_DIR / "outreach_timers.json"

    @staticmethod
    def _deadline_days(priority: str) -> int:
        return 3 if priority == "P0" else 5

    def _load_timers(self) -> list[dict[str, Any]]:
        if not self.TIMER_PATH.exists():
            return []
        try:
            raw = json.loads(self.TIMER_PATH.read_text(encoding="utf-8"))
            return raw if isinstance(raw, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save_timers(self, rows: list[dict[str, Any]]) -> None:
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.TIMER_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def _upsert_timer(self, timer: OutreachTimer) -> None:
        rows = self._load_timers()
        key = (timer.company_name, timer.contact_target)
        replaced = False
        for idx, row in enumerate(rows):
            if (row.get("company_name"), row.get("contact_target")) == key:
                rows[idx] = asdict(timer)
                replaced = True
                break
        if not replaced:
            rows.append(asdict(timer))
        self._save_timers(rows)

    def prepare_gmail_action(self, item: dict[str, Any]) -> ProposedAction:
        if item.get("status") not in {"approved", "approved_for_execution"}:
            raise PermissionError("Outreach item is not approved for execution.")
        if item.get("channel") != "email":
            raise ValueError("Only verified email outreach can create Gmail drafts.")

        to = str(item.get("contact_target") or "").strip()
        if "@" not in to:
            raise ValueError("Verified recipient email is required.")

        action = ProposedAction(
            action_type="gmail_draft",
            payload={
                "to": to,
                "subject": str(item.get("subject") or "").strip(),
                "body": str(item.get("message") or "").strip(),
            },
            reason=f"Approved outbound draft for {item.get('company_name','')}",
        )
        action.approve()
        return action

    def execute_approved_email(self, item: dict[str, Any], *, executor: ActionExecutor | None = None) -> dict[str, Any]:
        action = self.prepare_gmail_action(item)
        result = (executor or ActionExecutor()).execute(action)

        today = date.today()
        priority = str(item.get("priority") or "P1")
        deadline = today + timedelta(days=self._deadline_days(priority))
        timer = OutreachTimer(
            company_name=str(item.get("company_name") or ""),
            priority=priority,
            first_contact_date=today.isoformat(),
            last_contact_date=today.isoformat(),
            reply_deadline_date=deadline.isoformat(),
            channel="email",
            contact_target=str(item.get("contact_target") or ""),
        )
        self._upsert_timer(timer)

        return {
            "company_name": timer.company_name,
            "draft_result": result,
            "timer": asdict(timer),
            "note": "Gmail draft created. Sending still requires the user's final action unless a later explicitly approved send workflow is added.",
        }

    def register_web_contact_ready(self, item: dict[str, Any]) -> dict[str, Any]:
        if item.get("status") not in {"approved", "approved_for_execution"}:
            raise PermissionError("Outreach item is not approved for execution.")
        if item.get("channel") != "web_contact":
            raise ValueError("Item is not a web-contact outreach.")

        # Do not start a response timer before the human actually submits the form.
        return {
            "company_name": item.get("company_name", ""),
            "status": "waiting_for_human_submission",
            "contact_target": item.get("contact_target", ""),
            "message": item.get("message", ""),
            "timer_started": False,
        }
