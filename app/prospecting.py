from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Optional


@dataclass
class EvidenceMetric:
    value: Optional[float]
    source_url: str = ""
    source_name: str = ""
    observed_at: str = ""
    verified: bool = False

    def usable(self) -> bool:
        return self.value is not None and bool(self.source_url) and bool(self.source_name) and self.verified


@dataclass
class ProspectEvidence:
    company_name: str
    industry: str
    region: str = "福井県"
    industry_ai_dx_rate: Optional[EvidenceMetric] = None
    automation_need: Optional[EvidenceMetric] = None
    company_size_fit: Optional[EvidenceMetric] = None
    digital_maturity: Optional[EvidenceMetric] = None
    pain_signal: Optional[EvidenceMetric] = None
    agent_fit: Optional[EvidenceMetric] = None
    contactability: Optional[EvidenceMetric] = None
    evidence_summary: str = ""
    research_passes: int = 0
    independent_source_count: int = 0


@dataclass
class ProspectScore:
    company_name: str
    score: Optional[float]
    priority: str
    decision: str
    confidence: float
    reply_deadline_days: int
    max_followups: int
    cut_rule: str
    evidence_summary: str
    research_passes: int
    missing_evidence: list[str]


class ProspectScorer:
    """Scores only verified evidence. Missing metrics are never replaced with invented defaults."""

    WEIGHTS = {
        "industry_ai_dx_rate": 20,
        "automation_need": 20,
        "company_size_fit": 15,
        "digital_maturity": 10,
        "pain_signal": 15,
        "agent_fit": 15,
        "contactability": 5,
    }
    REQUIRED_FOR_SALES = {"industry_ai_dx_rate", "automation_need", "pain_signal", "agent_fit"}

    @staticmethod
    def _normalize(name: str, value: float) -> float:
        if name == "industry_ai_dx_rate":
            return max(0.0, min(100.0, value)) / 100.0
        return max(0.0, min(1.0, value))

    def score(self, p: ProspectEvidence) -> ProspectScore:
        metrics = {name: getattr(p, name) for name in self.WEIGHTS}
        usable = {name: metric for name, metric in metrics.items() if metric is not None and metric.usable()}
        missing = [name for name in self.WEIGHTS if name not in usable]
        missing_required = [name for name in self.REQUIRED_FOR_SALES if name not in usable]

        # Accuracy gate: a company cannot enter the sales list before two research passes.
        if p.research_passes < 2:
            return self._research_only(p, missing, "2回目の検証リサーチが未完了")
        if p.independent_source_count < 2:
            return self._research_only(p, missing, "独立した情報源が2件未満")
        if missing_required:
            return self._research_only(p, missing, "営業判断に必要な実測/検証済み根拠が不足")

        weighted_sum = 0.0
        available_weight = 0.0
        for name, metric in usable.items():
            weight = self.WEIGHTS[name]
            weighted_sum += self._normalize(name, float(metric.value)) * weight
            available_weight += weight

        if available_weight <= 0:
            return self._research_only(p, missing, "採点可能な検証済みデータなし")

        # Score is normalized only over evidence that actually exists; no fabricated zero/average values.
        score = (weighted_sum / available_weight) * 100.0
        coverage = available_weight / sum(self.WEIGHTS.values())
        source_factor = min(p.independent_source_count / 3.0, 1.0)
        confidence = coverage * source_factor

        if score >= 85 and confidence >= 0.80 and p.independent_source_count >= 3:
            priority, decision, deadline, followups = "P0", "最優先で営業", 3, 2
        elif score >= 70 and confidence >= 0.65 and p.independent_source_count >= 2:
            priority, decision, deadline, followups = "P1", "営業対象", 5, 2
        else:
            priority, decision, deadline, followups = "P2", "追加リサーチ後に判断", 7, 1

        return ProspectScore(
            company_name=p.company_name,
            score=round(score, 1),
            priority=priority,
            decision=decision,
            confidence=round(confidence * 100, 1),
            reply_deadline_days=deadline,
            max_followups=followups,
            cut_rule=self._cut_rule(priority),
            evidence_summary=p.evidence_summary,
            research_passes=p.research_passes,
            missing_evidence=missing,
        )

    def _research_only(self, p: ProspectEvidence, missing: list[str], reason: str) -> ProspectScore:
        return ProspectScore(
            company_name=p.company_name,
            score=None,
            priority="RESEARCH",
            decision=f"営業禁止: {reason}",
            confidence=0.0,
            reply_deadline_days=0,
            max_followups=0,
            cut_rule="営業せず、根拠を追加取得して2回目の検証を完了する。7日以内に検証できなければ保留/除外。",
            evidence_summary=p.evidence_summary,
            research_passes=p.research_passes,
            missing_evidence=missing,
        )

    @staticmethod
    def _cut_rule(priority: str) -> str:
        if priority == "P0":
            return "初回接触から3日で未返信なら1回目追客。さらに4日後に最終追客。最終追客から7日未返信でクローズ。"
        if priority == "P1":
            return "初回接触から5日で未返信なら1回目追客。さらに7日後に最終追客。最終追客から7日未返信でクローズ。"
        return "7日以内に追加根拠を取得して再採点。P1以上にならなければ保留/除外。"


class TwoPassResearchGate:
    """Forces discovery + independent verification before a prospect can be sold to."""

    @staticmethod
    def next_pass(p: ProspectEvidence) -> dict:
        if p.research_passes <= 0:
            return {
                "pass": 1,
                "action": "discovery",
                "instruction": "一次リサーチ: 公的統計、企業公式情報、求人/公開資料から事実と数値を収集し、URL・取得日を保存する。",
            }
        if p.research_passes == 1:
            return {
                "pass": 2,
                "action": "verification",
                "instruction": "二次リサーチ: 一次情報と独立した別ソースで数値・企業属性・課題シグナルを再確認し、矛盾があれば営業判定を停止する。",
            }
        return {
            "pass": p.research_passes,
            "action": "score",
            "instruction": "2回のリサーチ完了。検証済みデータだけでスコアリングする。",
        }


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
    def next_action(self, scored: ProspectScore, state: OutreachState, today: Optional[date] = None) -> dict:
        today = today or date.today()
        if scored.priority in {"RESEARCH", "P2", "DROP"}:
            return {"action": "close_or_research", "reason": "営業実行基準(P1以上)を満たしていない"}
        if state.explicitly_declined:
            return {"action": "close", "reason": "明確な辞退/不要回答"}
        if state.meeting_booked:
            return {"action": "prepare_meeting", "reason": "商談化済み"}
        if state.replied:
            return {"action": "review_reply", "reason": "返信あり。内容に応じて次工程へ"}

        last = date.fromisoformat(state.last_contact_date)
        elapsed = (today - last).days
        if state.followup_count >= scored.max_followups:
            if elapsed >= 7:
                return {"action": "close", "reason": "追客上限到達後7日間返信なし"}
            return {"action": "wait", "reason": "最終追客後の回答待ち", "review_date": str(last + timedelta(days=7))}

        wait_days = scored.reply_deadline_days if state.followup_count == 0 else (4 if scored.priority == "P0" else 7)
        if elapsed >= wait_days:
            return {"action": "prepare_followup", "reason": f"回答期限{wait_days}日を超過", "followup_number": state.followup_count + 1}
        return {"action": "wait", "reason": "回答期限内", "review_date": str(last + timedelta(days=wait_days))}


def to_dict(result: ProspectScore) -> dict:
    return asdict(result)
