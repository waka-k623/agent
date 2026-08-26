from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.connectors.base import Connector

CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


class GoogleCalendarConnector(Connector):
    """Read-only Google Calendar connector for Sales Agent v1."""

    def __init__(
        self,
        credentials_path: str | None = None,
        token_path: str | None = None,
        timezone: str | None = None,
    ) -> None:
        self.credentials_path = Path(
            credentials_path or os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
        )
        self.token_path = Path(
            token_path or os.getenv("GOOGLE_CALENDAR_TOKEN_PATH", "calendar_token.json")
        )
        self.timezone = timezone or os.getenv("APP_TIMEZONE", "Asia/Tokyo")
        self.scopes = [CALENDAR_READONLY_SCOPE]

    @property
    def name(self) -> str:
        return "google_calendar"

    def _credentials(self) -> Credentials:
        creds: Credentials | None = None

        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(self.token_path), self.scopes
            )

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.token_path.write_text(creds.to_json(), encoding="utf-8")

        if not creds or not creds.valid:
            if not self.credentials_path.exists():
                raise FileNotFoundError(
                    f"Google OAuth credentials not found: {self.credentials_path}."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path), self.scopes
            )
            creds = flow.run_local_server(port=0)
            self.token_path.write_text(creds.to_json(), encoding="utf-8")

        return creds

    def _service(self):
        return build("calendar", "v3", credentials=self._credentials())

    def healthcheck(self) -> dict[str, Any]:
        try:
            calendar = self._service().calendars().get(calendarId="primary").execute()
            return {
                "ok": True,
                "connector": self.name,
                "summary": calendar.get("summary"),
                "timezone": calendar.get("timeZone"),
            }
        except Exception as exc:
            return {"ok": False, "connector": self.name, "error": str(exc)}

    def list_upcoming_events(
        self,
        days: int = 7,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        tz = ZoneInfo(self.timezone)
        start = datetime.now(tz)
        end = start + timedelta(days=max(1, days))

        result = (
            self._service()
            .events()
            .list(
                calendarId="primary",
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=max(1, min(max_results, 250)),
            )
            .execute()
        )

        events: list[dict[str, Any]] = []
        for item in result.get("items", []):
            start_value = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
            end_value = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")
            events.append(
                {
                    "id": item.get("id"),
                    "summary": item.get("summary", ""),
                    "description": item.get("description", ""),
                    "location": item.get("location", ""),
                    "start": start_value,
                    "end": end_value,
                    "attendees": [
                        attendee.get("email")
                        for attendee in item.get("attendees", [])
                        if attendee.get("email")
                    ],
                    "status": item.get("status"),
                    "html_link": item.get("htmlLink"),
                }
            )
        return events

    def find_free_slots(
        self,
        days: int = 5,
        workday_start_hour: int = 9,
        workday_end_hour: int = 18,
        slot_minutes: int = 60,
    ) -> list[dict[str, str]]:
        tz = ZoneInfo(self.timezone)
        now = datetime.now(tz)
        events = self.list_upcoming_events(days=days, max_results=250)

        busy: list[tuple[datetime, datetime]] = []
        for event in events:
            start = event.get("start")
            end = event.get("end")
            if not start or not end or "T" not in start or "T" not in end:
                continue
            try:
                busy.append((datetime.fromisoformat(start), datetime.fromisoformat(end)))
            except ValueError:
                continue

        slots: list[dict[str, str]] = []
        for offset in range(days):
            day = (now + timedelta(days=offset)).date()
            cursor = datetime(day.year, day.month, day.day, workday_start_hour, tzinfo=tz)
            end_of_day = datetime(day.year, day.month, day.day, workday_end_hour, tzinfo=tz)

            if cursor < now:
                cursor = now.replace(second=0, microsecond=0)
                minute_mod = cursor.minute % slot_minutes
                if minute_mod:
                    cursor += timedelta(minutes=(slot_minutes - minute_mod))

            while cursor + timedelta(minutes=slot_minutes) <= end_of_day:
                candidate_end = cursor + timedelta(minutes=slot_minutes)
                overlaps = any(cursor < busy_end and candidate_end > busy_start for busy_start, busy_end in busy)
                if not overlaps:
                    slots.append(
                        {
                            "start": cursor.isoformat(),
                            "end": candidate_end.isoformat(),
                        }
                    )
                cursor = candidate_end

        return slots
