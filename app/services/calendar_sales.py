from __future__ import annotations

from typing import Any

from app.connectors.google_calendar import GoogleCalendarConnector
from app.providers.factory import get_llm_provider


CALENDAR_SALES_PROMPT = """You are Sales Agent v1.
You are given upcoming calendar events and available meeting slots.
Your job is to help a salesperson plan follow-up and meeting timing.
Return concise Japanese unless the input is clearly another language.
Do not claim to create, update, or send anything.
Use only the supplied calendar data.
Return:
- schedule_summary
- conflicts_or_risks
- recommended_meeting_slots (up to 3)
- recommended_follow_up_timing
- reasoning_summary
"""


def build_calendar_context(
    connector: GoogleCalendarConnector | None = None,
    days: int = 5,
) -> dict[str, Any]:
    calendar = connector or GoogleCalendarConnector()
    return {
        "events": calendar.list_upcoming_events(days=days),
        "free_slots": calendar.find_free_slots(days=days)[:20],
    }


def analyze_calendar_for_sales(
    user_request: str,
    connector: GoogleCalendarConnector | None = None,
    days: int = 5,
) -> str:
    context = build_calendar_context(connector=connector, days=days)
    provider = get_llm_provider()

    prompt = f"""User request:
{user_request}

Upcoming events:
{context['events']}

Available slots:
{context['free_slots']}
"""
    return provider.generate(CALENDAR_SALES_PROMPT, prompt)
