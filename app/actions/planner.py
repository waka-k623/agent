from __future__ import annotations

from email.utils import parseaddr
from typing import Any

from app.actions.approval import ProposedAction


class ActionPlanner:
    """Convert Sales Agent analysis into approval-required external actions."""

    def plan(self, analysis: dict[str, Any]) -> list[ProposedAction]:
        actions: list[ProposedAction] = []
        _, sender_email = parseaddr(str(analysis.get("sender", "")))
        subject = str(analysis.get("subject", ""))
        draft_message = str(analysis.get("draft_message", "")).strip()
        meeting_slots = analysis.get("meeting_slots") or []
        crm_status = str(analysis.get("crm_status", "")).strip()
        priority = str(analysis.get("priority", "")).strip()

        if sender_email and draft_message:
            actions.append(
                ProposedAction(
                    action_type="gmail_draft",
                    payload={
                        "to": sender_email,
                        "subject": self._reply_subject(subject),
                        "body": draft_message,
                        "thread_id": analysis.get("thread_id"),
                    },
                    reason="Sales Agent recommended a reply draft for this lead.",
                )
            )

        if meeting_slots and sender_email:
            first_slot = meeting_slots[0]
            end_slot = None
            if len(meeting_slots) > 1:
                end_slot = meeting_slots[1]

            actions.append(
                ProposedAction(
                    action_type="calendar_event",
                    payload={
                        "summary": f"Sales meeting: {sender_email}",
                        "start": first_slot,
                        "end": end_slot,
                        "attendees": [sender_email],
                        "description": analysis.get("current_status", ""),
                    },
                    reason="Sales Agent recommended scheduling a sales meeting.",
                )
            )

        if sender_email and (crm_status or priority):
            updates: dict[str, Any] = {}
            if crm_status:
                updates["status"] = crm_status
            if priority:
                updates["priority"] = priority

            actions.append(
                ProposedAction(
                    action_type="crm_update",
                    payload={
                        "email": sender_email,
                        "updates": updates,
                    },
                    reason="Sales Agent recommended updating the lead status in CRM.",
                )
            )

        return actions

    @staticmethod
    def _reply_subject(subject: str) -> str:
        clean = subject.strip()
        if not clean:
            return "Re:"
        if clean.lower().startswith("re:"):
            return clean
        return f"Re: {clean}"
