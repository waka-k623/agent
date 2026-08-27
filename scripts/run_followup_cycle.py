from __future__ import annotations

import json
from pathlib import Path

from app.followup_engine import FollowupEngine


OUTPUT = Path("data/latest_followup_cycle.json")


def main() -> None:
    decisions = FollowupEngine().run_active()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Follow-up decisions: {len(decisions)}")
    for item in decisions:
        print(f"[{item['priority']}] {item['company_name']} -> {item['action']} | {item['reason']}")
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    main()
