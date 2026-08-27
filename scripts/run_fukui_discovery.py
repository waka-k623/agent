from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.prospect_discovery import ProspectDiscovery


def load_strategy() -> dict:
    path = Path("data/strategy_state.json")
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def main() -> None:
    strategy = load_strategy()
    parser = argparse.ArgumentParser(description="Discover and research Fukui SME prospects using verified web evidence.")
    parser.add_argument("--industry", default="", help="Optional industry hint, e.g. 建設, 製造, 宿泊")
    parser.add_argument("--limit", type=int, default=None, help="Maximum companies to research this cycle")
    args = parser.parse_args()

    strategy_limit = int(strategy.get("max_new_prospects_next_cycle") or 10)
    limit = max(1, args.limit if args.limit is not None else strategy_limit)

    result = ProspectDiscovery().run(industry_hint=args.industry, research_limit=limit)
    result["strategy_applied"] = {
        "focus": strategy.get("focus", ""),
        "discovery_priority": strategy.get("discovery_priority", "balanced"),
        "research_limit": limit,
        "message_experiment_required": bool(strategy.get("message_experiment_required", False)),
    }

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
    print(f"Strategy research limit: {limit}")
    for item in result["sales_ready"]:
        score = item.get("score", {})
        print(f"- {item.get('company')}: {score.get('priority')} / {score.get('score')} / confidence {score.get('confidence')}%")


if __name__ == "__main__":
    main()
