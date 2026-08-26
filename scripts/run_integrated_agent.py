from __future__ import annotations

import json

from app.orchestrator import SalesAgentOrchestrator


def main() -> None:
    agent = SalesAgentOrchestrator()
    results = agent.analyze_inbox(max_results=10)

    print("\n=== Integrated Sales Agent ===\n")
    for index, item in enumerate(results, start=1):
        print(f"[{index}] {item.get('priority', 'low').upper()} | {item.get('subject', '')}")
        print(f"From: {item.get('sender', '')}")
        print(f"Category: {item.get('category', 'other')}")
        print(f"Status: {item.get('current_status', '')}")
        print(f"Next: {item.get('next_action', '')}")
        print(f"Timing: {item.get('recommended_timing', '')}")
        slots = item.get('meeting_slots') or []
        if slots:
            print("Meeting slots:")
            for slot in slots[:3]:
                print(f"  - {slot}")
        draft = item.get('draft_message', '')
        if draft:
            print("Draft:")
            print(draft)
        print("Context:")
        print(json.dumps(item.get('context_snapshot', {}), ensure_ascii=False))
        print("-" * 60)


if __name__ == "__main__":
    main()
