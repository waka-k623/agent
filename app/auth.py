from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["user", "admin"]


@dataclass(frozen=True)
class UserContext:
    username: str
    role: Role

    def can_approve_actions(self) -> bool:
        return self.role in {"user", "admin"}

    def can_view_audit_log(self) -> bool:
        return self.role == "admin"

    def can_manage_company_settings(self) -> bool:
        return self.role == "admin"


def require_admin(user: UserContext) -> None:
    if user.role != "admin":
        raise PermissionError("Administrator role required.")
