from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from app.runtime import RuntimeConfig


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    severity: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_preflight() -> list[CheckResult]:
    checks: list[CheckResult] = []
    runtime = RuntimeConfig.from_env()

    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "").strip()
        checks.append(CheckResult("AI Provider", bool(key), "OpenAI API key configured" if key else "OPENAI_API_KEY is missing"))
    elif provider == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        checks.append(CheckResult("AI Provider", bool(key), "Anthropic API key configured" if key else "ANTHROPIC_API_KEY is missing"))
    else:
        checks.append(CheckResult("AI Provider", False, f"Unsupported LLM_PROVIDER: {provider}"))

    credentials = Path(os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"))
    checks.append(CheckResult("Google OAuth credentials", credentials.exists(), f"Found {credentials}" if credentials.exists() else f"Missing {credentials}"))

    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "").strip()
    checks.append(CheckResult("Sheets CRM", bool(spreadsheet_id), "Spreadsheet ID configured" if spreadsheet_id else "GOOGLE_SHEETS_SPREADSHEET_ID is missing"))

    if runtime.is_demo:
        checks.append(CheckResult("Demo safety", not runtime.allow_live_writes, "Live writes disabled in demo" if not runtime.allow_live_writes else "Demo environment must not allow live writes"))
    else:
        checks.append(CheckResult("Production environment", True, "Production mode enabled", severity="warning"))
        checks.append(CheckResult("Live write gate", runtime.allow_live_writes, "Live writes enabled" if runtime.allow_live_writes else "Live writes disabled (safe default)", severity="warning"))

    admin_pw = os.getenv("DEMO_ADMIN_PASSWORD", "").strip()
    user_pw = os.getenv("DEMO_USER_PASSWORD", "").strip()
    if runtime.is_demo:
        checks.append(CheckResult("Demo login credentials", bool(admin_pw and user_pw), "Demo passwords configured" if admin_pw and user_pw else "Set DEMO_ADMIN_PASSWORD and DEMO_USER_PASSWORD before public deployment", severity="warning"))
    else:
        checks.append(CheckResult("Production login credentials", bool(admin_pw and user_pw), "Initial passwords configured" if admin_pw and user_pw else "Production passwords are not configured"))

    return checks


def summarize_preflight(checks: list[CheckResult]) -> dict[str, int | bool]:
    errors = sum(1 for c in checks if not c.ok and c.severity == "error")
    warnings = sum(1 for c in checks if not c.ok and c.severity == "warning")
    passed = sum(1 for c in checks if c.ok)
    return {
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
        "ready": errors == 0,
    }
