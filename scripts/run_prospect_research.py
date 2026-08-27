from __future__ import annotations

import json
from pathlib import Path

from app.providers.web_research_provider import TavilyWebResearchProvider
from app.research_cycle import ResearchCycle


INPUT_PATH = Path("data/prospect_candidates.json")
OUTPUT_PATH = Path("data/sales_ready_prospects.json")


def main() -> None:
    if not INPUT_PATH.exists():
        raise SystemExit(
            "data/prospect_candidates.json がありません。"
            "[{\"company_name\":\"...\",\"website\":\"...\",\"industry\":\"...\",\"region\":\"福井県\"}] の形式で作成してください。"
        )

    companies = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    if not isinstance(companies, list):
        raise SystemExit("prospect_candidates.json は配列形式である必要があります。")

    cycle = ResearchCycle(TavilyWebResearchProvider())
    results = cycle.run_batch(companies)
    sales_ready = [item for item in results if item["sales_eligible"]]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(sales_ready, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"調査企業数: {len(results)}")
    print(f"営業対象(P0/P1): {len(sales_ready)}")
    for item in sales_ready:
        score = item["score"]
        print(
            f"{score['priority']} | {item['company']} | "
            f"score={score['score']} | confidence={score['confidence']}%"
        )
    print(f"保存先: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
