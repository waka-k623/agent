from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    environment: str
    demo_mode_default: bool
    allow_live_writes: bool

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        environment = os.getenv("APP_ENV", "demo").strip().lower()
        demo_mode_default = os.getenv("DEMO_MODE_DEFAULT", "true").strip().lower() == "true"
        allow_live_writes = os.getenv("ALLOW_LIVE_WRITES", "false").strip().lower() == "true"
        return cls(
            environment=environment,
            demo_mode_default=demo_mode_default,
            allow_live_writes=allow_live_writes,
        )

    @property
    def is_demo(self) -> bool:
        return self.environment == "demo"

    def require_live_writes_enabled(self) -> None:
        if not self.allow_live_writes:
            raise PermissionError(
                "Live writes are disabled. Set ALLOW_LIVE_WRITES=true only in an explicitly approved production environment."
            )
