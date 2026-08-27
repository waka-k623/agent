from __future__ import annotations

import json
from pathlib import Path

from app.evidence_gap_research import EvidenceGapResearch

BOOTSTRAP = Path("data/bootstrap_fukui_candidates.json")
OUTPUT = Path("data/latest_evidence_gap_cycle.json")


def load_candidates() -> list[dict]:
    if not BOOTSTRAP.exists():
        return []
    raw = json.loads(BOOTSTRAP.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("companies", "candidates", "items"):
            if isinstance(raw.get(key), list):
                return raw[key]
    return []


def main() -> None:
    engine = EvidenceGapResearch()
    results = []
    for item in load_candidates():
        name = str(item.get("company_name") or item.get("name") or "").strip()
        website = str(item.get("website") or "").strip()
        if not name:
            continue
        results.append(engine.run_company(name, website))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
