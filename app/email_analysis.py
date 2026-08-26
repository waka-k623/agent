from __future__ import annotations

import json
from typing import Any

from app.providers.factory import get_llm_provider

ANALYSIS_PROMPT = """You are the email-analysis module for Sales Agent v1.
Analyze one email from the perspective of a salesperson.
Return ONLY valid JSON with these keys:
- is_sales_related: boolean
- category: one of [new_lead, reply_from_lead, follow_up_needed, meeting, proposal, admin, newsletter, other]
- priority: one of [high, medium, low]
- current_status: short string
- reasoning_summary: short explanation
- next_action: short action
- recommended_timing: short timing recommendation
- draft_message: a concise draft reply or empty string if no reply is needed
- requires_human_approval: boolean

Rules:
- Do not claim any message was sent.
- Treat external sending as requiring human approval.
- If the email is clearly a newsletter, automated notice, receipt, or unrelated personal message, usually mark is_sales_related=false.
- Use the same language as the email where practical.
"""


def analyze_email(email: dict[str, Any]) -> dict[str, Any]:
    provider = get_llm_provider()
    payload = {
        "from": email.get("from", ""),
        "to": email.get("to", ""),
        "subject": email.get("subject", ""),
        "date": email.get("date", ""),
        "snippet": email.get("snippet", ""),
        "body": email.get("body", "")[:12000],
    }
    raw = provider.generate(ANALYSIS_PROMPT, json.dumps(payload, ensure_ascii=False))
    return _parse_json(raw)


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)
