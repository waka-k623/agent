from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.prospect_discovery import ProspectDiscovery


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover and research Fukui SME prospects using verified web evidence.")
    parser.add_argument("--industry", default="", help="Optional industry hint, e.g. 建設, 製造, 宿泊")
    parser.add_argument("--limit", type=int, default=10, help="Maximum companies to research this cycle")
    args = parser.parse_args()

    result = ProspectDiscovery().run(industry_hint=args.industry, research_limit=max(1, args.limit))

    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)
    Path(out_dir / "latest_discovery_cycle.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    Path(out_dir / "sales_ready_prospects.json").write_text(
        json.dumps(result["sales_ready"], ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Discovered: {result['discovered_count']}")
    print(f"Researched: {result['researched_count']}")
    print(f"Sales-ready P0/P1: {result['sales_ready_count']}")
    for item in result["sales_ready"]:
        score = item.get("score", {})
        print(f"- {item.get('company')}: {score.get('priority')} / {score.get('score')} / confidence {score.get('confidence')}%")


if __name__ == "__main__":
    main()
