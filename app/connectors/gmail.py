from __future__ import annotations

import base64
import os
from email.header import decode_header
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.connectors.base import Connector

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class GmailConnector(Connector):
    """Read-only Gmail connector for Sales Agent v1."""

    def __init__(
        self,
        credentials_path: str | None = None,
        token_path: str | None = None,
    ) -> None:
        self.credentials_path = Path(
            credentials_path or os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
        )
        self.token_path = Path(
            token_path or os.getenv("GOOGLE_TOKEN_PATH", "token.json")
        )
        self.scopes = [GMAIL_READONLY_SCOPE]

    @property
    def name(self) -> str:
        return "gmail"

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
                    f"Google OAuth credentials not found: {self.credentials_path}. "
                    "Download a Desktop OAuth client JSON from Google Cloud and "
                    "save it at this path."
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path), self.scopes
            )
            creds = flow.run_local_server(port=0)
            self.token_path.write_text(creds.to_json(), encoding="utf-8")

        return creds

    def _service(self):
        return build("gmail", "v1", credentials=self._credentials())

    def healthcheck(self) -> dict[str, Any]:
        try:
            profile = (
                self._service().users().getProfile(userId="me").execute()
            )
            return {
                "ok": True,
                "connector": self.name,
                "email": profile.get("emailAddress"),
            }
        except Exception as exc:
            return {
                "ok": False,
                "connector": self.name,
                "error": str(exc),
            }

    def list_messages(
        self,
        query: str = "in:inbox",
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        max_results = max(1, min(max_results, 100))
        service = self._service()
        result = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )

        messages = result.get("messages", [])
        return [self.get_message(item["id"]) for item in messages]

    def get_message(self, message_id: str) -> dict[str, Any]:
        service = self._service()
        message = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

        payload = message.get("payload", {})
        headers = {
            h.get("name", "").lower(): self._decode_header(h.get("value", ""))
            for h in payload.get("headers", [])
        }

        return {
            "id": message.get("id"),
            "thread_id": message.get("threadId"),
            "label_ids": message.get("labelIds", []),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "subject": headers.get("subject", ""),
            "date": headers.get("date", ""),
            "snippet": message.get("snippet", ""),
            "body": self._extract_text(payload),
        }

    @staticmethod
    def _decode_header(value: str) -> str:
        decoded_parts = []
        for part, charset in decode_header(value):
            if isinstance(part, bytes):
                decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded_parts.append(part)
        return "".join(decoded_parts)

    def _extract_text(self, payload: dict[str, Any]) -> str:
        mime_type = payload.get("mimeType", "")
        body_data = payload.get("body", {}).get("data")

        if mime_type == "text/plain" and body_data:
            return self._decode_body(body_data)

        for part in payload.get("parts", []) or []:
            text = self._extract_text(part)
            if text:
                return text

        if body_data:
            return self._decode_body(body_data)

        return ""

    @staticmethod
    def _decode_body(data: str) -> str:
        padding = "=" * (-len(data) % 4)
        decoded = base64.urlsafe_b64decode(data + padding)
        return decoded.decode("utf-8", errors="replace")
