from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.connectors.base import Connector

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"

DEFAULT_HEADERS = [
    "lead_id",
    "company_name",
    "contact_name",
    "email",
    "source",
    "status",
    "priority",
    "last_contact_at",
    "next_follow_up_at",
    "notes",
]


class SheetsCRMConnector(Connector):
    """Google Sheets-backed lightweight CRM for Sales Agent v1."""

    def __init__(
        self,
        spreadsheet_id: str | None = None,
        sheet_name: str | None = None,
        credentials_path: str | None = None,
        token_path: str | None = None,
    ) -> None:
        self.spreadsheet_id = spreadsheet_id or os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
        self.sheet_name = sheet_name or os.getenv("GOOGLE_SHEETS_SHEET_NAME", "Leads")
        self.credentials_path = Path(credentials_path or os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"))
        self.token_path = Path(token_path or os.getenv("GOOGLE_SHEETS_TOKEN_PATH", "sheets_token.json"))
        self.scopes = [SHEETS_SCOPE]

    @property
    def name(self) -> str:
        return "sheets_crm"

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

    def _service(self):
        return build("sheets", "v4", credentials=self._credentials())

    def healthcheck(self) -> dict[str, Any]:
        try:
            if not self.spreadsheet_id:
                return {"ok": False, "connector": self.name, "error": "GOOGLE_SHEETS_SPREADSHEET_ID is not set"}
            meta = self._service().spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
            return {"ok": True, "connector": self.name, "title": meta.get("properties", {}).get("title", "")}
        except Exception as exc:
            return {"ok": False, "connector": self.name, "error": str(exc)}

    def ensure_headers(self) -> None:
        service = self._service()
        result = service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.sheet_name}!1:1",
        ).execute()
        values = result.get("values", [])
        if not values or values[0] != DEFAULT_HEADERS:
            service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A1:J1",
                valueInputOption="RAW",
                body={"values": [DEFAULT_HEADERS]},
            ).execute()

    def list_leads(self) -> list[dict[str, Any]]:
        self.ensure_headers()
        result = self._service().spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.sheet_name}!A2:J",
        ).execute()
        rows = result.get("values", [])
        leads = []
        for row in rows:
            padded = row + [""] * (len(DEFAULT_HEADERS) - len(row))
            leads.append(dict(zip(DEFAULT_HEADERS, padded)))
        return leads

    def append_lead(self, lead: dict[str, Any]) -> dict[str, Any]:
        self.ensure_headers()
        row = [[str(lead.get(header, "")) for header in DEFAULT_HEADERS]]
        result = self._service().spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.sheet_name}!A:J",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": row},
        ).execute()
        return {"ok": True, "updated_range": result.get("updates", {}).get("updatedRange")}

    def find_lead_by_email(self, email: str) -> dict[str, Any] | None:
        email_normalized = email.strip().lower()
        for lead in self.list_leads():
            if str(lead.get("email", "")).strip().lower() == email_normalized:
                return lead
        return None
