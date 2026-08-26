from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Literal

Role = Literal["user", "admin"]


@dataclass(frozen=True)
class UserContext:
    username: str
    role: Role
    company_id: str = "default"
    display_name: str = ""

    def can_approve_actions(self) -> bool:
        return self.role in {"user", "admin"}

    def can_view_audit_log(self) -> bool:
        return self.role == "admin"

    def can_manage_company_settings(self) -> bool:
        return self.role == "admin"


@dataclass
class UserRecord:
    username: str
    password_hash: str
    password_salt: str
    role: Role = "user"
    company_id: str = "default"
    display_name: str = ""
    active: bool = True

    def to_context(self) -> UserContext:
        return UserContext(
            username=self.username,
            role=self.role,
            company_id=self.company_id,
            display_name=self.display_name,
        )


class UserStore:
    """Simple local JSON user store for demo/local deployments."""

    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path or os.getenv("USER_DB_PATH", "data/users.json"))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, users: dict[str, dict[str, Any]]) -> None:
        self.path.write_text(
            json.dumps(users, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def ensure_demo_users(self) -> None:
        if self._load():
            return
        self.create_user(
            username="admin",
            password=os.getenv("DEMO_ADMIN_PASSWORD", "change-me-admin"),
            role="admin",
            company_id="default",
            display_name="Demo Admin",
        )
        self.create_user(
            username="sales",
            password=os.getenv("DEMO_USER_PASSWORD", "change-me-user"),
            role="user",
            company_id="default",
            display_name="Demo Sales",
        )

    def create_user(
        self,
        username: str,
        password: str,
        role: Role = "user",
        company_id: str = "default",
        display_name: str = "",
    ) -> UserRecord:
        username = username.strip()
        if not username:
            raise ValueError("username is required")
        if len(password) < 8:
            raise ValueError("password must be at least 8 characters")

        users = self._load()
        if username in users:
            raise ValueError("username already exists")

        salt = secrets.token_hex(16)
        record = UserRecord(
            username=username,
            password_hash=self._hash_password(password, salt),
            password_salt=salt,
            role=role,
            company_id=company_id,
            display_name=display_name,
            active=True,
        )
        users[username] = asdict(record)
        self._save(users)
        return record

    def authenticate(self, username: str, password: str) -> UserRecord | None:
        data = self._load().get(username.strip())
        if not data or not data.get("active", True):
            return None
        expected = str(data.get("password_hash", ""))
        salt = str(data.get("password_salt", ""))
        actual = self._hash_password(password, salt)
        if not hmac.compare_digest(expected, actual):
            return None
        return UserRecord(**data)

    def list_users(self) -> list[UserRecord]:
        return [UserRecord(**data) for data in self._load().values()]

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            200_000,
        ).hex()


def require_admin(user: UserContext) -> None:
    if user.role != "admin":
        raise PermissionError("Administrator role required.")
