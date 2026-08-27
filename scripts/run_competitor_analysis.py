from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from app.competitor_engine import CompetitorEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Run evidence-based competitor analysis for one active prospect.")
    parser.add_argument("--company", required=True)
    parser.add_argument("--industry", required=True)
    parser.add_argument("--need", required=True)
    parser.add_argument("--our-offer", required=True, dest="our_offer")
    args = parser.parse_args()

    result = CompetitorEngine().analyze(
        prospect_company=args.company,
        industry=args.industry,
        need=args.need,
        our_verified_offer=args.our_offer,
    )

    out = Path("data")
    out.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(ch for ch in args.company if ch.isalnum() or ch in {"-", "_"}) or "prospect"
    path = out / f"competitor_analysis_{safe_name}.json"
    path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Prospect: {result.prospect_company}")
    print(f"Verified competitors: {len(result.competitors)}")
    print(f"Positioning suggestions: {len(result.recommended_positioning)}")
    print(f"Evidence gaps: {len(result.evidence_gap)}")
    print(f"Saved: {path}")


if __name__ == "__main__":
    main()
