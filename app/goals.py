from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
import json


@dataclass
class SalesGoal:
    id: str
    title: str
    target_date: str
    target_wins: int
    region: str
    segment: str
    status: str = "active"
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now().isoformat(timespec="seconds")


@dataclass
class SalesMetrics:
    prospects: int = 0
    outreaches: int = 0
    replies: int = 0
    meetings: int = 0
    proposals: int = 0
    wins: int = 0


class GoalEngine:
    """Minimal goal/KPI engine for the autonomous sales-agent loop."""

    DEFAULT_PATH = Path("data/goals.json")

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self.DEFAULT_PATH

    def default_goal(self) -> SalesGoal:
        return SalesGoal(
            id="fukui-smb-first-win-2026-09",
            title="福井県の中小企業から1件以上受注する",
            target_date="2026-09-27",
            target_wins=1,
            region="福井県",
            segment="中小企業",
        )

    def load_or_create(self) -> SalesGoal:
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return SalesGoal(**raw)
        goal = self.default_goal()
        self.save(goal)
        return goal

    def save(self, goal: SalesGoal) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(goal), ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def initial_kpi_targets(goal: SalesGoal) -> SalesMetrics:
        # Initial funnel hypothesis. These values should later be recalibrated from actual conversion data.
        multiplier = max(goal.target_wins, 1)
        return SalesMetrics(
            prospects=100 * multiplier,
            outreaches=60 * multiplier,
            replies=10 * multiplier,
            meetings=5 * multiplier,
            proposals=3 * multiplier,
            wins=goal.target_wins,
        )

    @staticmethod
    def days_remaining(goal: SalesGoal) -> int:
        deadline = date.fromisoformat(goal.target_date)
        return max((deadline - date.today()).days, 0)

    def evaluate(self, goal: SalesGoal, actual: SalesMetrics) -> dict:
        targets = self.initial_kpi_targets(goal)
        remaining = self.days_remaining(goal)
        achieved = actual.wins >= goal.target_wins

        if achieved:
            health = "achieved"
            next_focus = "受注要因を記録し、再現可能な勝ちパターンとして整理する"
        elif actual.meetings == 0 and remaining <= 14:
            health = "at_risk"
            next_focus = "商談創出を最優先し、ターゲット・訴求・接触量を見直す"
        elif actual.replies == 0 and actual.outreaches >= 20:
            health = "at_risk"
            next_focus = "初回メッセージとターゲット選定を改善する"
        else:
            health = "in_progress"
            next_focus = "ファネルを進め、実績データを蓄積する"

        return {
            "goal": asdict(goal),
            "targets": asdict(targets),
            "actual": asdict(actual),
            "days_remaining": remaining,
            "health": health,
            "next_focus": next_focus,
        }

    def daily_plan(self, goal: SalesGoal, actual: SalesMetrics) -> list[str]:
        evaluation = self.evaluate(goal, actual)
        targets = SalesMetrics(**evaluation["targets"])
        tasks: list[str] = []

        if actual.prospects < targets.prospects:
            tasks.append("福井県の中小企業候補を追加し、優先順位を付ける")
        if actual.outreaches < targets.outreaches:
            tasks.append("優先度の高い見込み企業向けに個別営業案を作成する")
        if actual.replies > actual.meetings:
            tasks.append("返信済み見込み客から商談化できる案件を抽出する")
        if actual.meetings > actual.proposals:
            tasks.append("商談済み案件の提案・フォローアップを準備する")
        if actual.proposals > actual.wins:
            tasks.append("提案済み案件の失注リスクと次の追客タイミングを確認する")

        tasks.append(evaluation["next_focus"])
        return list(dict.fromkeys(tasks))
