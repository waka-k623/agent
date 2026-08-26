from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from email.utils import parseaddr
from typing import Any

from app.company_config import CompanyConfig, CompanyConfigStore
from app.connectors.google_calendar import GoogleCalendarConnector
from app.connectors.contacts import GoogleContactsConnector
from app.connectors.gmail import GmailConnector
from app.connectors.sheets_crm import SheetsCRMConnector
from app.providers.factory import get_llm_provider


@dataclass
class SalesContext:
    company: dict[str, Any]
    email: dict[str, Any]
    contact: dict[str, Any] | None
    crm_lead: dict[str, Any] | None
    calendar_events: list[dict[str, Any]]
    available_slots: list[dict[str, Any]]


class SalesAgentOrchestrator:
    """Coordinates Gmail, Contacts, Sheets CRM and Calendar for one sales decision."""

    SYSTEM_PROMPT = """You are Sales Agent v1 for a human salesperson.
Use both the COMPANY CONFIGURATION and BUSINESS CONTEXT supplied by the application.
The company configuration is authoritative for product scope, ideal customers, sales rules, tone, qualification criteria and forbidden claims.
Never invent company facts, pricing, results, guarantees or customer references.
Never claim that an email was sent, a calendar event was created, or CRM data was changed unless that action actually happened.
External writes require human approval.
Return ONLY valid JSON with these keys:
{
  "sales_relevant": true,
  "category": "new_lead|reply_from_lead|follow_up_needed|meeting|proposal|other",
  "priority": "high|medium|low",
  "current_status": "short status",
  "reasoning_summary": "brief business rationale",
  "next_action": "specific next action",
  "recommended_timing": "when to act",
  "meeting_slots": ["candidate ISO datetime", "candidate ISO datetime"],
  "draft_message": "draft reply or empty string",
  "crm_status": "new|contacted|replied|meeting_scheduled|meeting_completed|proposal_sent|follow_up|won|lost|",
  "requires_human_approval": true
}
Use contact/CRM/calendar context when available. Prefer concrete recommendations over generic advice.
"""

    def __init__(self, company_id: str = "default") -> None:
        self.company: CompanyConfig = CompanyConfigStore().load(company_id)
        self.gmail = GmailConnector()
        self.contacts = GoogleContactsConnector()
        self.crm = SheetsCRMConnector()
        self.calendar = GoogleCalendarConnector()
        self.provider = get_llm_provider()

    def build_context(self, message: dict[str, Any]) -> SalesContext:
        _, sender_email = parseaddr(message.get("from", ""))
        contact = self.contacts.find_by_email(sender_email) if sender_email else None
        crm_lead = self.crm.find_lead_by_email(sender_email) if sender_email else None

        calendar_events = self.calendar.list_upcoming_events(max_results=20)
        available_slots = self.calendar.find_free_slots(days=7, slot_minutes=60)

        return SalesContext(
            company=self.company.to_prompt_context(),
            email=message,
            contact=contact,
            crm_lead=crm_lead,
            calendar_events=calendar_events,
            available_slots=available_slots[:8],
        )

    def analyze_message(self, message: dict[str, Any]) -> dict[str, Any]:
        context = self.build_context(message)
        prompt = (
            "Analyze this sales situation using the company configuration and all available context.\n\n"
            + json.dumps(asdict(context), ensure_ascii=False, default=str)
        )
        raw = self.provider.generate(self.SYSTEM_PROMPT, prompt)
        result = self._parse_json(raw)
        result["message_id"] = message.get("id")
        result["thread_id"] = message.get("thread_id")
        result["sender"] = message.get("from", "")
        result["subject"] = message.get("subject", "")
        result["company_id"] = self.company.id
        result["company_name"] = self.company.company_name
        result["context_snapshot"] = {
            "contact_found": context.contact is not None,
            "crm_lead_found": context.crm_lead is not None,
            "calendar_event_count": len(context.calendar_events),
            "available_slot_count": len(context.available_slots),
        }
        return result

    def analyze_inbox(self, query: str = "in:inbox newer_than:14d", max_results: int = 10) -> list[dict[str, Any]]:
        messages = self.gmail.list_messages(query=query, max_results=max_results)
        results = [self.analyze_message(message) for message in messages]
        priority_rank = {"high": 0, "medium": 1, "low": 2}
        results.sort(
            key=lambda item: (
                not bool(item.get("sales_relevant", False)),
                priority_rank.get(str(item.get("priority", "low")).lower(), 9),
            )
        )
        return results

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {
                "sales_relevant": False,
                "category": "other",
                "priority": "low",
                "current_status": "Could not parse structured analysis",
                "reasoning_summary": raw[:1000],
                "next_action": "Review manually",
                "recommended_timing": "now",
                "meeting_slots": [],
                "draft_message": "",
                "crm_status": "",
                "requires_human_approval": True,
            }
