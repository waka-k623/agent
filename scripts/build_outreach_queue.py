from __future__ import annotations

import json
from pathlib import Path

from app.outreach_planner import OutreachPlanner


INPUT = Path("data/sales_ready_prospects.json")
OUTPUT = Path("data/outreach_approval_queue.json")


def main() -> None:
    if not INPUT.exists():
        raise SystemExit(f"Missing input: {INPUT}. Run the discovery/research cycle first.")

    raw = json.loads(INPUT.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("prospects", [])

    plans = OutreachPlanner(company_id="default").plan_batch(items)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(plans, ensure_ascii=False, indent=2), encoding="utf-8")

    ready = [p for p in plans if p.get("status") == "ready_for_approval"]
    blocked = [p for p in plans if p.get("status") != "ready_for_approval"]

    print(f"ready_for_approval={len(ready)} blocked={len(blocked)}")
    for plan in ready:
        print(f"[{plan['priority']}] {plan['company_name']} -> {plan['channel']} {plan['contact_target']}")


if __name__ == "__main__":
    main()
