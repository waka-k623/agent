from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.pdca_engine import KPICollector, PDCAEngine

DATA = Path("data")


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def as_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("items", "records", "results", "prospects"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def build_strategy(pdca: dict) -> dict:
    actual = pdca.get("actual", {})
    focus = str(pdca.get("focus") or "")

    strategy = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "focus": focus,
        "discovery_priority": "balanced",
        "outreach_priority": "P0_then_P1",
        "research_mode": "two_pass_verified_only",
        "max_new_prospects_next_cycle": 20,
        "message_experiment_required": False,
        "meeting_conversion_focus": False,
        "proposal_focus": False,
        "notes": [],
    }

    if actual.get("outreaches", 0) >= 10 and actual.get("replies", 0) == 0:
        strategy["discovery_priority"] = "higher_fit_only"
        strategy["max_new_prospects_next_cycle"] = 10
        strategy["message_experiment_required"] = True
        strategy["notes"].append("接触量を増やすより、P0/P1の根拠品質と初回訴求の比較検証を優先")
    elif actual.get("replies", 0) > 0 and actual.get("meetings", 0) == 0:
        strategy["meeting_conversion_focus"] = True
        strategy["notes"].append("新規発掘より返信済み案件の商談化を優先")
    elif actual.get("meetings", 0) > 0 and actual.get("proposals", 0) == 0:
        strategy["proposal_focus"] = True
        strategy["notes"].append("商談後の提案化を最優先")
    elif actual.get("proposals", 0) > 0 and actual.get("wins", 0) == 0:
        strategy["notes"].append("新規接触より提案済み案件の障壁確認と追客を優先")
    else:
        strategy["notes"].append("現在のファネルを継続し、実測データを蓄積")

    return strategy


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)

    # Persisted outputs only. Missing files mean zero observed activity, not estimated activity.
    memories = as_list(read_json(DATA / "prospect_memory.json", []))
    outreach = as_list(read_json(DATA / "outreach_approval_queue.json", []))
    followups = as_list(read_json(DATA / "latest_followup_cycle.json", []))

    snapshot = KPICollector.from_records(memories, outreach, followups)
    pdca = PDCAEngine().evaluate(snapshot)
    strategy = build_strategy(pdca)

    report = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "pdca": pdca,
        "strategy": strategy,
        "next_actions": [],
    }

    # The runner creates work; it does not silently send external messages.
    if pdca["actual"]["outreaches"] == 0:
        report["next_actions"].append("候補発掘・二重検証・P0/P1営業案生成を実行する")
    if pdca["focus"]:
        report["next_actions"].append(pdca["focus"])
    if pdca["experiments"]:
        report["next_actions"].append("PDCA改善実験を承認キューへ追加する")

    (DATA / "strategy_state.json").write_text(
        json.dumps(strategy, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (DATA / "latest_daily_sales_cycle.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
