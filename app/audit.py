from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


@dataclass
class AuditEvent:
    event_type: str
    company_id: str
    action_id: str
    action_type: str
    actor: str
    status: str
    timestamp: str
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    subject: str = ""
    sender: str = ""


class AuditLogger:
    """Append-only local JSONL audit log for approvals, rejections and executions."""

    def __init__(self, path: str | None = None, timezone: str | None = None) -> None:
        self.path = Path(path or os.getenv("AUDIT_LOG_PATH", "data/audit_log.jsonl"))
        self.timezone = timezone or os.getenv("APP_TIMEZONE", "Asia/Tokyo")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        *,
        event_type: str,
        company_id: str,
        action_id: str,
        action_type: str,
        actor: str,
        status: str,
        payload: dict[str, Any],
        result: dict[str, Any] | None = None,
        error: str | None = None,
        subject: str = "",
        sender: str = "",
    ) -> AuditEvent:
        timestamp = datetime.now(ZoneInfo(self.timezone)).isoformat(timespec="seconds")
        event = AuditEvent(
            event_type=event_type,
            company_id=company_id,
            action_id=action_id,
            action_type=action_type,
            actor=actor,
            status=status,
            timestamp=timestamp,
            payload=payload,
            result=result,
            error=error,
            subject=subject,
            sender=sender,
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event), ensure_ascii=False, default=str) + "\n")
        return event

    def list_events(self, limit: int = 200) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        events: list[dict[str, Any]] = []
        for line in lines[-max(1, limit):]:
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        events.reverse()
        return events
