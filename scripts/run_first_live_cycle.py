from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from app.prospect_discovery import ProspectDiscovery

DATA = Path("data")


def require_env() -> tuple[bool, list[str]]:
    missing: list[str] = []
    if not os.getenv("TAVILY_API_KEY"):
        missing.append("TAVILY_API_KEY")

    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider in {"anthropic", "claude"}:
        if not os.getenv("ANTHROPIC_API_KEY"):
            missing.append("ANTHROPIC_API_KEY")
    else:
        if not os.getenv("OPENAI_API_KEY"):
            missing.append("OPENAI_API_KEY")

    return (len(missing) == 0, missing)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    ready, missing = require_env()

    report = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "first_live_cycle",
        "ready": ready,
        "missing": missing,
        "result": None,
    }

    if not ready:
        report["status"] = "blocked_missing_credentials"
        report["instruction"] = (
            "不足しているAPIキーを環境変数へ設定後に再実行してください。"
            "不足値を推測・補完して調査を続行することは禁止します。"
        )
    else:
        try:
            result = ProspectDiscovery().run(research_limit=3)
            report["status"] = "completed"
            report["result"] = {
                "discovered_count": result.get("discovered_count", 0),
                "researched_count": result.get("researched_count", 0),
                "sales_ready_count": result.get("sales_ready_count", 0),
                "sales_ready": result.get("sales_ready", []),
            }
        except Exception as exc:
            report["status"] = "failed_safely"
            report["error_type"] = type(exc).__name__
            report["error"] = str(exc)

    output = DATA / "first_live_cycle_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
