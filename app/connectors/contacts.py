from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.connectors.base import Connector

CONTACTS_READONLY_SCOPE = "https://www.googleapis.com/auth/contacts.readonly"
PERSON_FIELDS = "names,emailAddresses,phoneNumbers,organizations"


class GoogleContactsConnector(Connector):
    """Read-only Google Contacts connector using the People API."""

    def __init__(
        self,
        credentials_path: str | None = None,
        token_path: str | None = None,
    ) -> None:
        self.credentials_path = Path(
            credentials_path or os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
        )
        self.token_path = Path(
            token_path or os.getenv("GOOGLE_CONTACTS_TOKEN_PATH", "contacts_token.json")
        )
        self.scopes = [CONTACTS_READONLY_SCOPE]

    @property
    def name(self) -> str:
        return "google_contacts"

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
                    f"Google OAuth credentials not found: {self.credentials_path}"
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path), self.scopes
            )
            creds = flow.run_local_server(port=0)
            self.token_path.write_text(creds.to_json(), encoding="utf-8")

        return creds

    def _service(self):
        return build("people", "v1", credentials=self._credentials())

    def healthcheck(self) -> dict[str, Any]:
        try:
            response = (
                self._service()
                .people()
                .connections()
                .list(
                    resourceName="people/me",
                    pageSize=1,
                    personFields="names,emailAddresses",
                )
                .execute()
            )
            return {
                "ok": True,
                "connector": self.name,
                "sample_count": len(response.get("connections", [])),
            }
        except Exception as exc:
            return {
                "ok": False,
                "connector": self.name,
                "error": str(exc),
            }

    def list_contacts(self, page_size: int = 200) -> list[dict[str, Any]]:
        page_size = max(1, min(page_size, 500))
        service = self._service()
        contacts: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            request = (
                service.people()
                .connections()
                .list(
                    resourceName="people/me",
                    pageSize=page_size,
                    pageToken=page_token,
                    personFields=PERSON_FIELDS,
                )
            )
            response = request.execute()
            contacts.extend(
                self._normalize_person(person)
                for person in response.get("connections", [])
            )
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return contacts

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        target = email.strip().lower()
        if not target:
            return None

        for contact in self.list_contacts():
            emails = [item.lower() for item in contact.get("emails", [])]
            if target in emails:
                return contact
        return None

    @staticmethod
    def _normalize_person(person: dict[str, Any]) -> dict[str, Any]:
        names = person.get("names", []) or []
        emails = person.get("emailAddresses", []) or []
        phones = person.get("phoneNumbers", []) or []
        organizations = person.get("organizations", []) or []

        primary_name = names[0] if names else {}
        primary_org = organizations[0] if organizations else {}

        return {
            "resource_name": person.get("resourceName", ""),
            "display_name": primary_name.get("displayName", ""),
            "given_name": primary_name.get("givenName", ""),
            "family_name": primary_name.get("familyName", ""),
            "emails": [item.get("value", "") for item in emails if item.get("value")],
            "phone_numbers": [
                item.get("value", "") for item in phones if item.get("value")
            ],
            "organization": primary_org.get("name", ""),
            "title": primary_org.get("title", ""),
            "department": primary_org.get("department", ""),
        }
