from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

DATA = Path("data")


@dataclass
class MasterStepResult:
    step: str
    status: str
    reason: str = ""
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""


class MasterAgent:
    """Top-level orchestrator for the full sales-agent lifecycle.

    Principles:
    - Missing credentials/data cause a safe skip, never fabricated execution.
    - Customer-facing sends and price changes remain human-approval gated.
    - Each sub-agent persists its own outputs; this layer coordinates them.
    - The master cycle always ends with KPI/PDCA and executive reporting.
    """

    def __init__(self, data_dir: Path = DATA) -> None:
        self.data = data_dir
        self.data.mkdir(parents=True, exist_ok=True)

    @property
    def has_ai(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))

    @property
    def has_web(self) -> bool:
        return bool(os.getenv("TAVILY_API_KEY")) and self.has_ai

    @property
    def has_google(self) -> bool:
        credentials = os.getenv("GOOGLE_CREDENTIALS_PATH", "")
        return bool(credentials and Path(credentials).exists())

    @property
    def has_db(self) -> bool:
        return bool(os.getenv("DATABASE_URL"))

    def exists(self, name: str) -> bool:
        return (self.data / name).exists()

    def run_step(self, name: str, command: list[str], *, enabled: bool, reason: str = "") -> MasterStepResult:
        if not enabled:
            return MasterStepResult(step=name, status="skipped", reason=reason)
        completed = subprocess.run(command, capture_output=True, text=True)
        return MasterStepResult(
            step=name,
            status="ok" if completed.returncode == 0 else "error",
            reason=reason,
            returncode=completed.returncode,
            stdout=completed.stdout[-5000:],
            stderr=completed.stderr[-5000:],
        )

    def build_plan(self) -> list[tuple[str, list[str], bool, str]]:
        py = sys.executable
        return [
            (
                "prospect_discovery_and_research",
                [py, "scripts/run_fukui_discovery.py"],
                self.has_web,
                "実Web+LLM認証がある場合のみ福井企業の発掘と二重検証を実行",
            ),
            (
                "evidence_gap_research",
                [py, "scripts/run_evidence_gap_cycle.py"],
                self.has_web and self.exists("bootstrap_verified_evidence.json"),
                "不足根拠だけを別ソースで再検証",
            ),
            (
                "promotion_to_sales_queue",
                [py, "scripts/run_promotion_cycle.py"],
                self.has_ai and (self.exists("latest_evidence_gap_cycle.json") or self.exists("sales_ready_prospects.json")),
                "P0/P1だけ営業承認キューへ昇格",
            ),
            (
                "gmail_reply_and_followup_bridge",
                [py, "scripts/run_gmail_followup_bridge.py"],
                self.has_google and self.has_ai,
                "送信済み案件の返信を読み、追客/商談/CLOSEを判定",
            ),
            (
                "tracking_cycle",
                [py, "scripts/run_tracking_cycle.py"],
                self.exists("sent_outreach.json"),
                "送信済み案件の回答期限と追客上限を管理",
            ),
            (
                "kpi_pdca",
                [py, "scripts/run_daily_sales_cycle.py"],
                True,
                "観測済み営業実績だけからKPIと次の重点施策を更新",
            ),
            (
                "executive_dashboard",
                [py, "scripts/run_executive_dashboard.py"],
                True,
                "KGI・ファネル・期待売上・重点アクションを集約",
            ),
        ]

    def run(self) -> dict[str, Any]:
        started = datetime.now().isoformat(timespec="seconds")
        results: list[MasterStepResult] = []
        for name, command, enabled, reason in self.build_plan():
            result = self.run_step(name, command, enabled=enabled, reason=reason)
            results.append(result)

        errors = [r.step for r in results if r.status == "error"]
        report = {
            "run_at": started,
            "mode": "master_agent",
            "kgi_policy": "goal_driven_sales_with_human_approval_for_external_writes",
            "capabilities": {
                "web_research": self.has_web,
                "ai_reasoning": self.has_ai,
                "google_tracking": self.has_google,
                "persistent_memory": self.has_db,
            },
            "guardrails": {
                "fabricated_metrics": "forbidden",
                "research_verification_passes": 2,
                "external_send": "human_approval_required",
                "customer_price_change": "human_approval_required",
                "p0_p1_only_for_sales": True,
            },
            "steps": [asdict(r) for r in results],
            "status": "error" if errors else "ok",
            "errors": errors,
            "next_human_actions": self._next_human_actions(results),
        }
        (self.data / "latest_master_agent_cycle.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return report

    def _next_human_actions(self, results: list[MasterStepResult]) -> list[str]:
        actions: list[str] = []
        if not self.has_web:
            actions.append("TAVILY_API_KEYとLLM APIキーを接続するとライブ企業調査が有効になります")
        if not self.has_google:
            actions.append("Google認証を接続するとGmail返信追跡が有効になります")
        if self.exists("outreach_approval_queue.json"):
            actions.append("営業承認キューを確認し、送信対象だけ承認してください")
        if self.exists("latest_pricing_recommendation.json"):
            actions.append("価格提案は顧客提示前に人間承認してください")
        if any(r.status == "error" for r in results):
            actions.append("エラー工程のログを確認してください")
        return actions
