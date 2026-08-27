from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DATA = Path("data")


def run_step(name: str, command: list[str], enabled: bool) -> dict:
    if not enabled:
        return {"step": name, "status": "skipped"}
    completed = subprocess.run(command, capture_output=True, text=True)
    return {
        "step": name,
        "status": "ok" if completed.returncode == 0 else "error",
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)

    has_ai = bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
    has_web = bool(os.getenv("TAVILY_API_KEY")) and has_ai
    has_google = bool(os.getenv("GOOGLE_CREDENTIALS_PATH") and Path(os.getenv("GOOGLE_CREDENTIALS_PATH", "")).exists())

    steps = []

    # 1. Prospect discovery / two-pass research. Never runs without real web + LLM credentials.
    steps.append(run_step(
        "prospect_discovery",
        [sys.executable, "scripts/run_fukui_discovery.py"],
        enabled=has_web,
    ))

    # 2. Build personalized outreach plans from verified P0/P1 research.
    sales_ready_exists = (DATA / "sales_ready_prospects.json").exists()
    steps.append(run_step(
        "outreach_planning",
        [sys.executable, "scripts/build_outreach_queue.py"],
        enabled=has_ai and sales_ready_exists,
    ))

    # 3. Check replies and follow-up deadlines only when Google credentials are present.
    outreach_exists = (DATA / "outreach_approval_queue.json").exists()
    steps.append(run_step(
        "followup_cycle",
        [sys.executable, "scripts/run_followup_cycle.py"],
        enabled=has_google and outreach_exists,
    ))

    # 4. KPI / PDCA always runs. Missing stages remain zero/unknown; no fabricated values.
    steps.append(run_step(
        "kpi_pdca",
        [sys.executable, "scripts/run_daily_sales_cycle.py"],
        enabled=True,
    ))

    report = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "autonomous_prepare_and_review",
        "external_send_policy": "human_approval_required",
        "capabilities": {
            "web_research": has_web,
            "ai_generation": has_ai,
            "google_reply_tracking": has_google,
            "postgres_memory": bool(os.getenv("DATABASE_URL")),
        },
        "steps": steps,
    }
    (DATA / "latest_autonomous_cycle.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if any(step.get("status") == "error" for step in steps):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
