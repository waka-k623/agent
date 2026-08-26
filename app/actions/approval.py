from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
import uuid

ActionType = Literal["gmail_draft", "calendar_event", "crm_update"]


@dataclass
class ProposedAction:
    action_type: ActionType
    payload: dict[str, Any]
    reason: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    approved: bool = False

    def approve(self) -> None:
        self.approved = True

    def require_approval(self) -> None:
        if not self.approved:
            raise PermissionError(
                f"Action {self.id} ({self.action_type}) requires explicit human approval."
            )
