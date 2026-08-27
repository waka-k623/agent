from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Optional

from app.connectors.gmail import GmailConnector
from app.prospect_memory import ProspectMemoryRecord, ProspectMemoryStore
from app.prospecting import OutreachState, ProspectLifecycle, ProspectScore
from app.providers.factory import get_llm_provider


@dataclass
class ReplyAssessment:
    status: str
    positive: bool = False
    explicitly_declined: bool = False
    meeting_intent: bool = False
    proposal_interest: bool = False
    summary: str = ""


@dataclass
class FollowupDecision:
    company_name: str
    priority: str
    action: str
    reason: str
    review_date: str = ""
    reply_summary: str = ""
    followup_message: str = ""
    status: str = "pending"


class FollowupEngine:
    """Track replies and decide the next action for active P0/P1 prospects.

    Rules:
    - Gmail is read-only here; no message is sent automatically.
    - Explicit rejection closes the prospect immediately.
    - Follow-up cadence is delegated to ProspectLifecycle.
    - Generated follow-up copy must not invent facts or outcomes.
    """

    def __init__(
        self,
        gmail: GmailConnector | None = None,
        memory: ProspectMemoryStore | None = None,
    ) -> None:
        self.gmail = gmail or GmailConnector()
        self.memory = memory or ProspectMemoryStore()
        self.lifecycle = ProspectLifecycle()
        self.llm = get_llm_provider()

    @staticmethod
    def _score_from_record(record: ProspectMemoryRecord) -> ProspectScore:
        priority = record.priority
        if priority == "P0":
            deadline, followups = 3, 2
            cut_rule = "初回接触から3日で未返信なら1回目追客。さらに4日後に最終追客。最終追客から7日未返信でクローズ。"
        elif priority == "P1":
            deadline, followups = 5, 2
            cut_rule = "初回接触から5日で未返信なら1回目追客。さらに7日後に最終追客。最終追客から7日未返信でクローズ。"
        else:
            deadline, followups = 0, 0
            cut_rule = "営業実行対象外"

        return ProspectScore(
            company_name=record.company_name,
            score=record.score,
            priority=record.priority,
            decision="",
            confidence=record.confidence,
            reply_deadline_days=deadline,
            max_followups=followups,
            cut_rule=cut_rule,
            evidence_summary=str(record.evidence.get("evidence_summary", "")),
            research_passes=record.research_passes,
            missing_evidence=[],
        )

    def _find_reply(self, record: ProspectMemoryRecord) -> Optional[dict[str, Any]]:
        evidence = record.evidence or {}
        contact_email = str(evidence.get("contact_email") or "").strip()
        if not contact_email:
            for key in ("email", "contact_email"):
                value = str(getattr(record, key, "") or "").strip()
                if value:
                    contact_email = value
                    break
        if not contact_email:
            return None

        query = f'from:{contact_email}'
        messages = self.gmail.list_messages(query=query, max_results=20)
        if not messages:
            return None

        if record.last_contact_at:
            try:
                threshold = datetime.fromisoformat(record.last_contact_at[:19])
            except ValueError:
                threshold = None
        else:
            threshold = None

        for message in messages:
            # Gmail Date header parsing is intentionally avoided here because formats vary.
            # If we cannot reliably compare dates, newest matching message is treated as candidate.
            if message.get("from"):
                return message
        return None

    def _classify_reply(self, message: dict[str, Any]) -> ReplyAssessment:
        body = str(message.get("body") or message.get("snippet") or "").strip()
        if not body:
            return ReplyAssessment(status="unknown", summary="返信本文を取得できませんでした")

        system_prompt = (
            "You classify Japanese B2B sales replies. Use only the supplied reply text. "
            "Do not infer hidden intent. Return strict JSON only."
        )
        user_message = json.dumps(
            {
                "reply": body,
                "required_output": {
                    "status": "positive|neutral|declined|meeting|proposal_interest|unknown",
                    "positive": "boolean",
                    "explicitly_declined": "boolean",
                    "meeting_intent": "boolean",
                    "proposal_interest": "boolean",
                    "summary": "short Japanese factual summary",
                },
            },
            ensure_ascii=False,
        )
        raw = self.llm.generate(system_prompt, user_message).strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return ReplyAssessment(status="unknown", summary="返信分類に失敗しました")

        return ReplyAssessment(
            status=str(data.get("status") or "unknown"),
            positive=bool(data.get("positive", False)),
            explicitly_declined=bool(data.get("explicitly_declined", False)),
            meeting_intent=bool(data.get("meeting_intent", False)),
            proposal_interest=bool(data.get("proposal_interest", False)),
            summary=str(data.get("summary") or ""),
        )

    def _build_followup(self, record: ProspectMemoryRecord, followup_number: int) -> str:
        evidence_summary = str(record.evidence.get("evidence_summary", ""))
        system_prompt = (
            "Write a concise Japanese B2B follow-up email. Use only supplied facts. "
            "Do not invent names, metrics, pain points, urgency, case studies, or claims. "
            "Keep it polite and low-pressure. Return only the message body."
        )
        user_message = json.dumps(
            {
                "company_name": record.company_name,
                "priority": record.priority,
                "followup_number": followup_number,
                "verified_context": evidence_summary,
                "instruction": "前回連絡への簡潔なフォローアップ。返信を強要しない。",
            },
            ensure_ascii=False,
        )
        return self.llm.generate(system_prompt, user_message).strip()

    def evaluate_record(self, record: ProspectMemoryRecord, today: Optional[date] = None) -> FollowupDecision:
        if record.priority not in {"P0", "P1"}:
            return FollowupDecision(
                company_name=record.company_name,
                priority=record.priority,
                action="skip",
                reason="P0/P1ではないため追跡対象外",
                status="closed",
            )

        reply = self._find_reply(record)
        assessment = self._classify_reply(reply) if reply else None

        followup_count = int(record.evidence.get("followup_count", 0) or 0)
        first_contact = record.evidence.get("first_contact_date") or (record.last_contact_at[:10] if record.last_contact_at else date.today().isoformat())
        last_contact = record.evidence.get("last_contact_date") or (record.last_contact_at[:10] if record.last_contact_at else first_contact)

        state = OutreachState(
            first_contact_date=str(first_contact),
            last_contact_date=str(last_contact),
            followup_count=followup_count,
            replied=bool(assessment),
            meeting_booked=bool(assessment and assessment.meeting_intent),
            proposal_sent=bool(record.evidence.get("proposal_sent", False)),
            explicitly_declined=bool(assessment and assessment.explicitly_declined),
        )
        scored = self._score_from_record(record)
        lifecycle = self.lifecycle.next_action(scored, state, today=today)
        action = lifecycle.get("action", "wait")

        if assessment and assessment.explicitly_declined:
            record.status = "closed"
            record.exclusion_reason = "明確な辞退/不要回答"
        elif assessment and assessment.meeting_intent:
            record.status = "meeting"
        elif assessment:
            record.status = "replied"

        followup_message = ""
        if action == "prepare_followup":
            followup_number = int(lifecycle.get("followup_number", followup_count + 1))
            followup_message = self._build_followup(record, followup_number)
            record.evidence["pending_followup_number"] = followup_number
            record.evidence["pending_followup_message"] = followup_message
        elif action == "close":
            record.status = "closed"

        if assessment:
            record.evidence["latest_reply_assessment"] = asdict(assessment)

        review_date = str(lifecycle.get("review_date") or "")
        if review_date:
            record.next_review_at = review_date
        self.memory.upsert(record)

        return FollowupDecision(
            company_name=record.company_name,
            priority=record.priority,
            action=action,
            reason=str(lifecycle.get("reason") or ""),
            review_date=review_date,
            reply_summary=assessment.summary if assessment else "",
            followup_message=followup_message,
            status=record.status,
        )

    def run_active(self) -> list[dict[str, Any]]:
        active = [r for r in self.memory.list_records() if r.priority in {"P0", "P1"} and r.status not in {"closed", "won"}]
        decisions = [asdict(self.evaluate_record(record)) for record in active]
        order = {"prepare_meeting": 0, "review_reply": 1, "prepare_followup": 2, "wait": 3, "close": 4, "skip": 5}
        return sorted(decisions, key=lambda d: (order.get(d["action"], 9), 0 if d["priority"] == "P0" else 1))
