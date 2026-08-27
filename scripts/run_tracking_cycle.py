from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.outreach_tracking import OutreachLifecycleOrchestrator, SentOutreachStore


def main() -> None:
    store = SentOutreachStore()
    records = store.list_records()
    results = OutreachLifecycleOrchestrator().evaluate_all(records)

    report = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "tracked_count": len(records),
        "results": results,
        "summary": {
            "prepare_followup": sum(1 for r in results if r.get("action") == "prepare_followup"),
            "prepare_meeting": sum(1 for r in results if r.get("action") == "prepare_meeting"),
            "review_reply": sum(1 for r in results if r.get("action") == "review_reply"),
            "wait": sum(1 for r in results if r.get("action") == "wait"),
            "close": sum(1 for r in results if r.get("action") == "close"),
        },
    }

    out = Path("data/latest_tracking_cycle.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
