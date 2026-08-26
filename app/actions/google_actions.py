from __future__ import annotations

import base64
import os
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.actions.approval import ProposedAction
from app.connectors.sheets_crm import SheetsCRMConnector

GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"


class GmailDraftAction:
    def __init__(self, credentials_path: str | None = None, token_path: str | None = None) -> None:
        self.credentials_path = Path(credentials_path or os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"))
        self.token_path = Path(token_path or os.getenv("GOOGLE_GMAIL_ACTION_TOKEN_PATH", "gmail_action_token.json"))
        self.scopes = [GMAIL_COMPOSE_SCOPE]

    def _credentials(self) -> Credentials:
        creds: Credentials | None = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), self.scopes)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.token_path.write_text(creds.to_json(), encoding="utf-8")
        if not creds or not creds.valid:
            if not self.credentials_path.exists():
                raise FileNotFoundError(f"Google OAuth credentials not found: {self.credentials_path}")
            flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), self.scopes)
            creds = flow.run_local_server(port=0)
            self.token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    def execute(self, action: ProposedAction) -> dict[str, Any]:
        action.require_approval()
        if action.action_type != "gmail_draft":
            raise ValueError("Wrong action type")
        payload = action.payload
        message = EmailMessage()
        message["To"] = payload["to"]
        message["Subject"] = payload.get("subject", "")
        if payload.get("in_reply_to"):
            message["In-Reply-To"] = payload["in_reply_to"]
            message["References"] = payload["in_reply_to"]
        message.set_content(payload.get("body", ""))
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        result = build("gmail", "v1", credentials=self._credentials()).users().drafts().create(
            userId="me", body={"message": {"raw": raw, **({"threadId": payload["thread_id"]} if payload.get("thread_id") else {})}}
        ).execute()
        return {"ok": True, "draft_id": result.get("id"), "message_id": result.get("message", {}).get("id")}


class CalendarEventAction:
    def __init__(self, credentials_path: str | None = None, token_path: str | None = None) -> None:
        self.credentials_path = Path(credentials_path or os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"))
        self.token_path = Path(token_path or os.getenv("GOOGLE_CALENDAR_ACTION_TOKEN_PATH", "calendar_action_token.json"))
        self.scopes = [CALENDAR_EVENTS_SCOPE]

    def _credentials(self) -> Credentials:
        creds: Credentials | None = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), self.scopes)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.token_path.write_text(creds.to_json(), encoding="utf-8")
        if not creds or not creds.valid:
            if not self.credentials_path.exists():
                raise FileNotFoundError(f"Google OAuth credentials not found: {self.credentials_path}")
            flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), self.scopes)
            creds = flow.run_local_server(port=0)
            self.token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    def execute(self, action: ProposedAction) -> dict[str, Any]:
        action.require_approval()
        if action.action_type != "calendar_event":
            raise ValueError("Wrong action type")
        payload = action.payload
        event = {
            "summary": payload["summary"],
            "description": payload.get("description", ""),
            "start": {"dateTime": payload["start"], "timeZone": payload.get("timezone", "Asia/Tokyo")},
            "end": {"dateTime": payload["end"], "timeZone": payload.get("timezone", "Asia/Tokyo")},
        }
        if payload.get("attendees"):
            event["attendees"] = [{"email": email} for email in payload["attendees"]]
        result = build("calendar", "v3", credentials=self._credentials()).events().insert(
            calendarId="primary", body=event, sendUpdates="none"
        ).execute()
        return {"ok": True, "event_id": result.get("id"), "html_link": result.get("htmlLink")}


class CRMUpdateAction:
    def __init__(self, crm: SheetsCRMConnector | None = None) -> None:
        self.crm = crm or SheetsCRMConnector()

    def execute(self, action: ProposedAction) -> dict[str, Any]:
        action.require_approval()
        if action.action_type != "crm_update":
            raise ValueError("Wrong action type")
        return self.crm.update_lead_by_email(action.payload["email"], action.payload.get("updates", {}))
