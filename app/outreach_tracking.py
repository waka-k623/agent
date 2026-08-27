from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
import json

from app.prospecting import ProspectLifecycle, ProspectScore, OutreachState


@dataclass
class SentOutreachRecord:
    company_name: str
    priority: str
    sent_at: str
    channel: str
    contact: str = ""
    thread_id: str = ""
    followup_count: int = 0
    status: str = "sent"
    replied: bool = False
    meeting_booked: bool = False
    proposal_sent: bool = False
    explicitly_declined: bool = False


class SentOutreachStore:
    DEFAULT_PATH = Path("data/sent_outreach.json")

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self.DEFAULT_PATH

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _save(self, rows: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def mark_sent(self, record: SentOutreachRecord) -> SentOutreachRecord:
        rows = self._load()
        key = (record.company_name, record.contact, record.channel)
        replaced = False
        for idx, row in enumerate(rows):
            row_key = (row.get("company_name"), row.get("contact", ""), row.get("channel", ""))
            if row_key == key:
                rows[idx] = asdict(record)
                replaced = True
                break
        if not replaced:
            rows.append(asdict(record))
        self._save(rows)
        return record

    def list_records(self) -> list[SentOutreachRecord]:
        return [SentOutreachRecord(**row) for row in self._load()]


class OutreachLifecycleOrchestrator:
    def __init__(self) -> None:
        self.lifecycle = ProspectLifecycle()

    @staticmethod
    def _score_from_record(record: SentOutreachRecord) -> ProspectScore:
        if record.priority == "P0":
            deadline, followups = 3, 2
        else:
            deadline, followups = 5, 2
        return ProspectScore(
            company_name=record.company_name,
            score=None,
            priority=record.priority,
            decision="tracking",
            confidence=100.0,
            reply_deadline_days=deadline,
            max_followups=followups,
            cut_rule="",
            evidence_summary="",
            research_passes=2,
            missing_evidence=[],
        )

    def evaluate(self, record: SentOutreachRecord, today: date | None = None) -> dict[str, Any]:
        sent_date = date.fromisoformat(record.sent_at[:10])
        state = OutreachState(
            first_contact_date=sent_date.isoformat(),
            last_contact_date=sent_date.isoformat(),
            followup_count=record.followup_count,
            replied=record.replied,
            meeting_booked=record.meeting_booked,
            proposal_sent=record.proposal_sent,
            explicitly_declined=record.explicitly_declined,
        )
        result = self.lifecycle.next_action(self._score_from_record(record), state, today=today)
        result.update({
            "company_name": record.company_name,
            "priority": record.priority,
            "sent_at": record.sent_at,
            "channel": record.channel,
            "contact": record.contact,
        })
        return result

    def evaluate_all(self, records: list[SentOutreachRecord], today: date | None = None) -> list[dict[str, Any]]:
        return [self.evaluate(r, today=today) for r in records]
