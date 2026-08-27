from __future__ import annotations

import json
from pathlib import Path

from app.promotion_engine import PromotionEngine

DATA = Path("data")


def read_json(path: Path):
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "records", "results"):
            if isinstance(data.get(key), list):
                return data[key]
        # Evidence gap runner may store records under companies.
        if isinstance(data.get("companies"), list):
            return data["companies"]
    return []


def main() -> None:
    scored_items = read_json(DATA / "latest_evidence_gap_cycle.json")
    result = PromotionEngine().promote(scored_items)

    out = DATA / "latest_promotion_cycle.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
