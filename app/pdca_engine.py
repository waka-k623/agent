from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from app.goals import GoalEngine, SalesMetrics


@dataclass
class FunnelSnapshot:
    prospects: int = 0
    outreaches: int = 0
    replies: int = 0
    meetings: int = 0
    proposals: int = 0
    wins: int = 0

    def metrics(self) -> SalesMetrics:
        return SalesMetrics(**asdict(self))


class KPICollector:
    """Build KPI counts only from persisted agent outputs; never invent missing activity."""

    @staticmethod
    def from_records(
        prospect_memories: list[dict[str, Any]],
        outreach_records: list[dict[str, Any]],
        followup_records: list[dict[str, Any]],
    ) -> FunnelSnapshot:
        prospect_names = {str(x.get("company_name") or "").strip() for x in prospect_memories if x.get("company_name")}
        outreach_names = {
            str(x.get("company_name") or "").strip()
            for x in outreach_records
            if x.get("company_name") and x.get("status") in {"approved", "sent", "demo_approved", "web_ready"}
        }
        reply_names, meeting_names, proposal_names, win_names = set(), set(), set(), set()
        for row in followup_records:
            company = str(row.get("company_name") or "").strip()
            if not company:
                continue
            classification = str(row.get("classification") or row.get("reply_classification") or "").lower()
            action = str(row.get("action") or "").lower()
            stage = str(row.get("stage") or "").lower()
            if classification and classification not in {"", "none", "no_reply"}:
                reply_names.add(company)
            if classification == "meeting" or action == "prepare_meeting" or stage == "meeting":
                meeting_names.add(company)
            if classification == "proposal_interest" or stage == "proposal":
                proposal_names.add(company)
            if stage in {"won", "win", "closed_won"}:
                win_names.add(company)
        return FunnelSnapshot(
            prospects=len(prospect_names),
            outreaches=len(outreach_names),
            replies=len(reply_names),
            meetings=len(meeting_names),
            proposals=len(proposal_names),
            wins=len(win_names),
        )


class PDCAEngine:
    """Chooses the next sales focus from observed funnel data. Strategy changes remain approval-gated."""

    def __init__(self) -> None:
        self.goals = GoalEngine()

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float | None:
        if denominator <= 0:
            return None
        return round((numerator / denominator) * 100, 1)

    def evaluate(self, snapshot: FunnelSnapshot) -> dict[str, Any]:
        goal = self.goals.load_or_create()
        base = self.goals.evaluate(goal, snapshot.metrics())
        rates = {
            "reply_rate": self._rate(snapshot.replies, snapshot.outreaches),
            "meeting_rate_from_replies": self._rate(snapshot.meetings, snapshot.replies),
            "proposal_rate_from_meetings": self._rate(snapshot.proposals, snapshot.meetings),
            "win_rate_from_proposals": self._rate(snapshot.wins, snapshot.proposals),
        }

        # Decisions use observed counts/rates only. No assumed conversion benchmark is inserted.
        experiments: list[dict[str, str]] = []
        if snapshot.outreaches == 0:
            focus = "P0/P1の営業候補を承認キューへ供給する"
        elif snapshot.outreaches >= 10 and snapshot.replies == 0:
            focus = "ターゲット選定と初回訴求を見直す"
            experiments.append({"hypothesis": "初回訴求または対象企業との適合が弱い可能性", "test": "検証済み根拠の異なる2種類の訴求案を作り、人間承認後に小規模比較する"})
        elif snapshot.replies > 0 and snapshot.meetings == 0:
            focus = "返信から商談へのCTAとフォローを改善する"
            experiments.append({"hypothesis": "返信は得られているが商談提案への移行に摩擦がある可能性", "test": "返信内容別に商談提案CTAを作り分ける"})
        elif snapshot.meetings > 0 and snapshot.proposals == 0:
            focus = "商談後の課題整理と提案化を優先する"
        elif snapshot.proposals > 0 and snapshot.wins == 0:
            focus = "提案済み案件の反論・決裁障壁・追客状況を確認する"
        else:
            focus = base["next_focus"]

        return {
            "date": date.today().isoformat(),
            "goal": base["goal"],
            "actual": asdict(snapshot),
            "rates": rates,
            "days_remaining": base["days_remaining"],
            "health": base["health"],
            "focus": focus,
            "experiments": experiments,
            "rule": "数値が存在しない指標は評価しない。戦略変更・外部送信は人間承認後に実行する。",
        }
