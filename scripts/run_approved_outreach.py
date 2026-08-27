from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.outreach_execution import OutreachExecutionManager

QUEUE = Path("data/outreach_approval_queue.json")
OUT = Path("data/latest_outreach_execution.json")


def load_queue() -> list[dict]:
    if not QUEUE.exists():
        return []
    try:
        data = json.loads(QUEUE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "records", "results"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute one approved outreach item safely.")
    parser.add_argument("--company", required=True, help="Exact company name in approval queue")
    args = parser.parse_args()

    items = load_queue()
    matches = [x for x in items if str(x.get("company_name") or "") == args.company]
    if not matches:
        raise SystemExit(f"Company not found in approval queue: {args.company}")

    item = matches[0]
    manager = OutreachExecutionManager()
    if item.get("channel") == "email":
        result = manager.execute_approved_email(item)
    elif item.get("channel") == "web_contact":
        result = manager.register_web_contact_ready(item)
    else:
        raise SystemExit(f"Unsupported channel: {item.get('channel')}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
