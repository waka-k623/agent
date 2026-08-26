from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any

from app.connectors.gmail import GmailConnector
from app.connectors.sheets_crm import SheetsCRMConnector
from app.sales_inbox import analyze_inbox


def _extract_email(value: str) -> str:
    return parseaddr(value)[1].strip().lower()


def _lead_id_from_email(email: str) -> str:
    safe = re.sub(r"[^a-z0-9]+", "-", email.lower()).strip("-")
    return f"lead-{safe}" if safe else f"lead-{int(datetime.now(timezone.utc).timestamp())}"


def sync_recent_sales_leads(max_results: int = 10) -> list[dict[str, Any]]:
    gmail = GmailConnector()
    crm = SheetsCRMConnector()
    analyses = analyze_inbox(max_results=max_results)
    created: list[dict[str, Any]] = []

    for item in analyses:
        if not item.get("is_sales_related"):
            continue

        sender = item.get("from", "")
        email = _extract_email(sender)
        if not email or crm.find_lead_by_email(email):
            continue

        lead = {
            "lead_id": _lead_id_from_email(email),
            "company_name": "",
            "contact_name": parseaddr(sender)[0],
            "email": email,
            "source": "gmail",
            "status": item.get("category", "new_lead"),
            "priority": item.get("priority", "medium"),
            "last_contact_at": item.get("date", ""),
            "next_follow_up_at": item.get("recommended_timing", ""),
            "notes": item.get("reasoning", ""),
        }
        crm.append_lead(lead)
        created.append(lead)

    return created
