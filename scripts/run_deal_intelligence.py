from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

DATA = Path("data")
INPUT = DATA / "opportunities.json"
OUTPUT = DATA / "latest_deal_intelligence.json"


def run(command: list[str]) -> dict:
    completed = subprocess.run(command, capture_output=True, text=True)
    return {
        "status": "ok" if completed.returncode == 0 else "error",
        "returncode": completed.returncode,
        "stdout": completed.stdout[-3000:],
        "stderr": completed.stderr[-3000:],
    }


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    if not INPUT.exists():
        report = {"status": "skipped", "reason": "data/opportunities.json が未作成", "deals": []}
        OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    raw = json.loads(INPUT.read_text(encoding="utf-8"))
    deals = raw if isinstance(raw, list) else raw.get("opportunities", []) if isinstance(raw, dict) else []
    results = []

    for deal in deals:
        if not isinstance(deal, dict):
            continue
        company = str(deal.get("company_name") or "").strip()
        if not company:
            continue
        row = {"company_name": company, "competitor_analysis": {"status": "skipped"}, "pricing": {"status": "skipped"}}

        industry = str(deal.get("industry") or "").strip()
        need = str(deal.get("need") or deal.get("pain_point") or "").strip()
        offer = str(deal.get("our_offer") or "").strip()
        if industry and need and offer:
            row["competitor_analysis"] = run([
                sys.executable, "scripts/run_competitor_analysis.py",
                "--company", company,
                "--industry", industry,
                "--need", need,
                "--our-offer", offer,
            ])
        else:
            row["competitor_analysis"] = {"status": "skipped", "reason": "industry/need/our_offer不足"}

        pricing = deal.get("pricing") if isinstance(deal.get("pricing"), dict) else {}
        command = [sys.executable, "scripts/run_pricing_optimization.py", "--company", company]
        mapping = {
            "delivery_cost_yen": "--delivery-cost",
            "estimated_hours": "--hours",
            "hourly_cost_yen": "--hourly-cost",
            "customer_budget_min_yen": "--budget-min",
            "customer_budget_max_yen": "--budget-max",
        }
        for key, flag in mapping.items():
            if pricing.get(key) is not None:
                command += [flag, str(pricing[key])]
        for key, flag in {
            "verified_competitor_prices_yen": "--competitor-prices",
            "historical_won_prices_yen": "--won-prices",
            "historical_lost_prices_yen": "--lost-prices",
        }.items():
            values = pricing.get(key)
            if isinstance(values, list) and values:
                command += [flag, ",".join(str(v) for v in values)]

        if pricing:
            row["pricing"] = run(command)
        else:
            row["pricing"] = {"status": "skipped", "reason": "pricing evidence不足"}
        results.append(row)

    report = {"status": "ok", "deals": results}
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
