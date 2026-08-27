from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.pricing_optimizer import PricingEvidence, PricingOptimizer, to_dict

DATA = Path("data")


def csv_ints(value: str | None) -> list[int]:
    if not value:
        return []
    return [int(x.strip()) for x in value.split(",") if x.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True)
    parser.add_argument("--delivery-cost", type=int)
    parser.add_argument("--hours", type=float)
    parser.add_argument("--hourly-cost", type=int)
    parser.add_argument("--budget-min", type=int)
    parser.add_argument("--budget-max", type=int)
    parser.add_argument("--competitor-prices")
    parser.add_argument("--won-prices")
    parser.add_argument("--lost-prices")
    args = parser.parse_args()

    evidence = PricingEvidence(
        company_name=args.company,
        delivery_cost_yen=args.delivery_cost,
        estimated_hours=args.hours,
        hourly_cost_yen=args.hourly_cost,
        customer_budget_min_yen=args.budget_min,
        customer_budget_max_yen=args.budget_max,
        verified_competitor_prices_yen=csv_ints(args.competitor_prices),
        historical_won_prices_yen=csv_ints(args.won_prices),
        historical_lost_prices_yen=csv_ints(args.lost_prices),
    )
    result = to_dict(PricingOptimizer().recommend(evidence))
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / "latest_pricing_recommendation.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
