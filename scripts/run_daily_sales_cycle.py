from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.pdca_engine import KPICollector, PDCAEngine

DATA = Path("data")


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def as_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("items", "records", "results", "prospects"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)

    # These are persisted outputs from earlier pipeline stages. Missing files mean zero observed activity,
    # not estimated activity.
    memories = as_list(read_json(DATA / "prospect_memory.json", []))
    outreach = as_list(read_json(DATA / "outreach_approval_queue.json", []))
    followups = as_list(read_json(DATA / "latest_followup_cycle.json", []))

    snapshot = KPICollector.from_records(memories, outreach, followups)
    pdca = PDCAEngine().evaluate(snapshot)

    report = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "pdca": pdca,
        "next_actions": [],
    }

    # The runner creates work; it does not silently send external messages.
    if pdca["actual"]["outreaches"] == 0:
        report["next_actions"].append("候補発掘・二重検証・P0/P1営業案生成を実行する")
    if pdca["focus"]:
        report["next_actions"].append(pdca["focus"])
    if pdca["experiments"]:
        report["next_actions"].append("PDCA改善実験を承認キューへ追加する")

    (DATA / "latest_daily_sales_cycle.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
