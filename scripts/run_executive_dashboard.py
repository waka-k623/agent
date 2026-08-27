from __future__ import annotations

import json
from pathlib import Path

from app.executive_dashboard import DealRecord, ExecutiveDashboard
from app.pdca_engine import FunnelSnapshot

DATA = Path("data")


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def as_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("items", "records", "results", "deals"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    daily = read_json(DATA / "latest_daily_sales_cycle.json", {})
    actual = ((daily or {}).get("pdca") or {}).get("actual") or {}
    snapshot = FunnelSnapshot(
        prospects=int(actual.get("prospects", 0) or 0),
        outreaches=int(actual.get("outreaches", 0) or 0),
        replies=int(actual.get("replies", 0) or 0),
        meetings=int(actual.get("meetings", 0) or 0),
        proposals=int(actual.get("proposals", 0) or 0),
        wins=int(actual.get("wins", 0) or 0),
    )

    raw_deals = as_list(read_json(DATA / "deals.json", []))
    deals = [
        DealRecord(
            company_name=str(x.get("company_name") or ""),
            stage=str(x.get("stage") or ""),
            proposed_price_yen=int(x["proposed_price_yen"]) if x.get("proposed_price_yen") is not None else None,
            probability_pct=float(x["probability_pct"]) if x.get("probability_pct") is not None else None,
            lost_reason=str(x.get("lost_reason") or ""),
        )
        for x in raw_deals if isinstance(x, dict)
    ]

    report = ExecutiveDashboard().build(snapshot, deals)
    path = DATA / "latest_executive_dashboard.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
