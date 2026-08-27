from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Optional


@dataclass
class ProspectEvidence:
    company_name: str
    industry: str
    region: str = "福井県"
    industry_ai_dx_rate: Optional[float] = None
    automation_need: float = 0.0
    company_size_fit: float = 0.0
    digital_maturity: float = 0.0
    pain_signal: float = 0.0
    agent_fit: float = 0.0
    contactability: float = 0.0
    evidence_confidence: float = 0.0
    evidence_summary: str = ""
    source_count: int = 0


@dataclass
class ProspectScore:
    company_name: str
    score: float
    priority: str
    decision: str
    confidence: float
    reply_deadline_days: int
    max_followups: int
    cut_rule: str
    evidence_summary: str


class ProspectScorer:
    """Evidence-based lead scoring. Inputs are normalized 0..1 except AI/DX rate (0..100)."""

    WEIGHTS = {
        "industry_ai_dx": 20,
        "automation_need": 20,
        "company_size_fit": 15,
        "digital_maturity": 10,
        "pain_signal": 15,
        "agent_fit": 15,
        "contactability": 5,
    }

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))

    def score(self, p: ProspectEvidence) -> ProspectScore:
        # AI/DX industry adoption is used as market evidence, not as a standalone buying signal.
        # Mid-to-high adoption receives credit while leaving room for an opportunity gap.
        rate = 50.0 if p.industry_ai_dx_rate is None else max(0.0, min(100.0, p.industry_ai_dx_rate))
        industry_ai_dx = rate / 100.0

        raw = (
            industry_ai_dx * self.WEIGHTS["industry_ai_dx"]
            + self._clamp(p.automation_need) * self.WEIGHTS["automation_need"]
            + self._clamp(p.company_size_fit) * self.WEIGHTS["company_size_fit"]
            + self._clamp(p.digital_maturity) * self.WEIGHTS["digital_maturity"]
            + self._clamp(p.pain_signal) * self.WEIGHTS["pain_signal"]
            + self._clamp(p.agent_fit) * self.WEIGHTS["agent_fit"]
            + self._clamp(p.contactability) * self.WEIGHTS["contactability"]
        )

        confidence = self._clamp(p.evidence_confidence)
        # Weak evidence cannot create a high-priority lead by itself.
        adjusted = raw * (0.70 + 0.30 * confidence)

        # Require multiple sources for top priority; this prevents single-source hallucination/overfit.
        if adjusted >= 85 and confidence >= 0.80 and p.source_count >= 3:
            priority, decision = "P0", "最優先で営業"
            deadline, followups = 3, 2
        elif adjusted >= 70 and confidence >= 0.65 and p.source_count >= 2:
            priority, decision = "P1", "営業対象"
            deadline, followups = 5, 2
        elif adjusted >= 55 and confidence >= 0.50:
            priority, decision = "P2", "追加リサーチ後に判断"
            deadline, followups = 7, 1
        else:
            priority, decision = "DROP", "営業対象外"
            deadline, followups = 0, 0

        if priority == "P0":
            cut_rule = "初回接触から3日で未返信なら1回目追客。さらに4日後に最終追客。最終追客から7日未返信でクローズ。"
        elif priority == "P1":
            cut_rule = "初回接触から5日で未返信なら1回目追客。さらに7日後に最終追客。最終追客から7日未返信でクローズ。"
        elif priority == "P2":
            cut_rule = "営業前に根拠を追加収集。7日以内にスコア70未満のままなら保留/除外。"
        else:
            cut_rule = "営業しない。新しい強い根拠が得られた場合のみ再評価。"

        return ProspectScore(
            company_name=p.company_name,
            score=round(adjusted, 1),
            priority=priority,
            decision=decision,
            confidence=round(confidence * 100, 1),
            reply_deadline_days=deadline,
            max_followups=followups,
            cut_rule=cut_rule,
            evidence_summary=p.evidence_summary,
        )


@dataclass
class OutreachState:
    first_contact_date: str
    last_contact_date: str
    followup_count: int = 0
    replied: bool = False
    meeting_booked: bool = False
    proposal_sent: bool = False
    explicitly_declined: bool = False


class ProspectLifecycle:
    """Decides whether to follow up, wait, escalate, or close a prospect."""

    def next_action(self, scored: ProspectScore, state: OutreachState, today: Optional[date] = None) -> dict:
        today = today or date.today()
        if scored.priority == "DROP":
            return {"action": "close", "reason": "スコア基準未達"}
        if state.explicitly_declined:
            return {"action": "close", "reason": "明確な辞退/不要回答"}
        if state.meeting_booked:
            return {"action": "prepare_meeting", "reason": "商談化済み"}
        if state.replied:
            return {"action": "review_reply", "reason": "返信あり。内容に応じて次工程へ"}

        last = date.fromisoformat(state.last_contact_date)
        elapsed = (today - last).days

        if state.followup_count >= scored.max_followups:
            # Give a final grace period after the last permitted follow-up.
            if elapsed >= 7:
                return {"action": "close", "reason": "追客上限到達後7日間返信なし"}
            return {"action": "wait", "reason": "最終追客後の回答待ち", "review_date": str(last + timedelta(days=7))}

        wait_days = scored.reply_deadline_days if state.followup_count == 0 else (4 if scored.priority == "P0" else 7)
        if elapsed >= wait_days:
            return {
                "action": "prepare_followup",
                "reason": f"回答期限{wait_days}日を超過",
                "followup_number": state.followup_count + 1,
            }
        return {
            "action": "wait",
            "reason": "回答期限内",
            "review_date": str(last + timedelta(days=wait_days)),
        }


def to_dict(result: ProspectScore) -> dict:
    return asdict(result)
