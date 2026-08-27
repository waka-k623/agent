from __future__ import annotations

import json

from app.master_agent import MasterAgent


def main() -> None:
    report = MasterAgent().run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("status") == "error":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
