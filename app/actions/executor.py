from __future__ import annotations

from typing import Any

from app.actions.approval import ProposedAction
from app.actions.google_actions import CalendarEventAction, CRMUpdateAction, GmailDraftAction
from app.runtime import RuntimeConfig


class ActionExecutor:
    """Executes only explicitly approved external actions in a write-enabled environment."""

    def __init__(self, runtime: RuntimeConfig | None = None) -> None:
        self.runtime = runtime or RuntimeConfig.from_env()
        self.gmail = GmailDraftAction()
        self.calendar = CalendarEventAction()
        self.crm = CRMUpdateAction()

    def execute(self, action: ProposedAction) -> dict[str, Any]:
        action.require_approval()
        self.runtime.require_live_writes_enabled()

        if action.action_type == "gmail_draft":
            return self.gmail.execute(action)
        if action.action_type == "calendar_event":
            return self.calendar.execute(action)
        if action.action_type == "crm_update":
            return self.crm.execute(action)

        raise ValueError(f"Unsupported action type: {action.action_type}")
