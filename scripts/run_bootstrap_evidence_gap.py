from __future__ import annotations

import json
from pathlib import Path

SOURCE = Path("data/bootstrap_verified_evidence.json")
OUTPUT = Path("data/bootstrap_evidence_gap_report.json")


def main() -> None:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    companies = data.get("companies", [])
    report = {
        "market_context": data.get("market_context", {}),
        "companies": [],
        "sales_ready": [],
        "research_required": [],
        "rule": "公開情報で直接確認できない項目は推測せず、営業判定を保留する。",
    }

    for company in companies:
        missing = list(company.get("missing_for_sales_decision", []))
        item = {
            "company_name": company.get("company_name"),
            "industry": company.get("industry"),
            "employee_count": company.get("employee_count"),
            "dx_initiative": company.get("dx_initiative"),
            "verified_contact": company.get("verified_contact"),
            "evidence_gap": missing,
            "status": "RESEARCH" if missing else "READY_FOR_SCORING",
            "next_research_tasks": [
                f"{field} を企業公式情報・求人情報・公的資料の独立ソース2件以上で確認する"
                for field in missing
            ],
        }
        report["companies"].append(item)
        if missing:
            report["research_required"].append(item)
        else:
            report["sales_ready"].append(item)

    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
