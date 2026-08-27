from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional
import json


@dataclass
class ProspectMemoryRecord:
    company_key: str
    company_name: str
    industry: str = ""
    region: str = "福井県"
    website: str = ""
    status: str = "research"
    priority: str = "RESEARCH"
    score: Optional[float] = None
    confidence: float = 0.0
    research_passes: int = 0
    first_seen_at: str = ""
    last_researched_at: str = ""
    last_scored_at: str = ""
    last_contact_at: str = ""
    next_review_at: str = ""
    source_urls: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    exclusion_reason: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        if not self.first_seen_at:
            self.first_seen_at = now


class ProspectMemoryStore:
    """Persistent memory for researched companies.

    The next research cycle should reuse stored facts and refresh only stale,
    missing, or contradictory evidence rather than starting from zero.
    """

    DEFAULT_PATH = Path("data/prospect_memory.json")

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self.DEFAULT_PATH

    def _load_all(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}

    def _save_all(self, data: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def company_key(company_name: str, website: str = "") -> str:
        base = website.strip().lower().rstrip("/") or company_name.strip().lower()
        return base.replace(" ", "")

    def get(self, company_name: str, website: str = "") -> Optional[ProspectMemoryRecord]:
        key = self.company_key(company_name, website)
        item = self._load_all().get(key)
        return ProspectMemoryRecord(**item) if item else None

    def upsert(self, record: ProspectMemoryRecord) -> ProspectMemoryRecord:
        data = self._load_all()
        existing = data.get(record.company_key, {})

        # Preserve unique sources and merge evidence instead of overwriting history blindly.
        merged_sources = list(dict.fromkeys(existing.get("source_urls", []) + record.source_urls))
        merged_evidence = dict(existing.get("evidence", {}))
        merged_evidence.update(record.evidence)

        merged = dict(existing)
        merged.update(asdict(record))
        merged["source_urls"] = merged_sources
        merged["evidence"] = merged_evidence
        if existing.get("first_seen_at"):
            merged["first_seen_at"] = existing["first_seen_at"]

        data[record.company_key] = merged
        self._save_all(data)
        return ProspectMemoryRecord(**merged)

    def list_records(self) -> list[ProspectMemoryRecord]:
        return [ProspectMemoryRecord(**item) for item in self._load_all().values()]

    def search(self, *, region: str = "", status: str = "", priority: str = "") -> list[ProspectMemoryRecord]:
        records = self.list_records()
        if region:
            records = [r for r in records if r.region == region]
        if status:
            records = [r for r in records if r.status == status]
        if priority:
            records = [r for r in records if r.priority == priority]
        return records

    def research_plan(self, record: ProspectMemoryRecord, stale_after_days: int = 30) -> dict[str, Any]:
        """Return a delta-research plan using stored memory.

        Verified evidence may be reused if still fresh. Missing/stale fields are refreshed.
        A previous exclusion is not forgotten, but can be re-opened if new evidence appears.
        """
        today = date.today()
        stale = True
        if record.last_researched_at:
            try:
                last = date.fromisoformat(record.last_researched_at[:10])
                stale = (today - last).days >= stale_after_days
            except ValueError:
                stale = True

        known_fields = [k for k, v in record.evidence.items() if v not in (None, "", [], {})]
        missing_fields = [
            key for key in (
                "industry_ai_dx_rate",
                "automation_need",
                "company_size_fit",
                "digital_maturity",
                "pain_signal",
                "agent_fit",
                "contactability",
            ) if key not in record.evidence
        ]

        if record.research_passes < 2:
            mode = "continue_verification"
        elif stale:
            mode = "refresh_stale_evidence"
        elif missing_fields:
            mode = "fill_missing_evidence"
        else:
            mode = "reuse_memory_and_check_changes"

        return {
            "company_key": record.company_key,
            "mode": mode,
            "known_fields": known_fields,
            "missing_fields": missing_fields,
            "existing_sources": record.source_urls,
            "previous_priority": record.priority,
            "previous_score": record.score,
            "previous_exclusion_reason": record.exclusion_reason,
            "instruction": (
                "保存済みの検証済み情報を再利用し、欠損・古い・矛盾のある項目だけ追加調査する。"
                "同じURLだけで再検証せず、必要に応じて独立した新しい情報源を取得する。"
            ),
        }

    def mark_researched(self, record: ProspectMemoryRecord) -> ProspectMemoryRecord:
        record.last_researched_at = datetime.now().isoformat(timespec="seconds")
        return self.upsert(record)

    def mark_scored(self, record: ProspectMemoryRecord, *, score: Optional[float], priority: str, confidence: float, exclusion_reason: str = "") -> ProspectMemoryRecord:
        record.score = score
        record.priority = priority
        record.confidence = confidence
        record.exclusion_reason = exclusion_reason
        record.last_scored_at = datetime.now().isoformat(timespec="seconds")
        record.status = "closed" if priority == "DROP" else ("research" if priority in {"RESEARCH", "P2"} else "active")
        return self.upsert(record)
