from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class JsonStateStore:
    """Small state store with Postgres when DATABASE_URL is available, JSON fallback otherwise."""

    def __init__(self, namespace: str, json_path: str) -> None:
        self.namespace = namespace
        self.json_path = Path(json_path)
        self.database_url = os.getenv("DATABASE_URL", "").strip()

    def _connect(self):
        import psycopg
        return psycopg.connect(self.database_url)

    def _ensure_table(self, conn) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_state (
                    namespace TEXT NOT NULL,
                    state_key TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY(namespace, state_key)
                )
                """
            )
        conn.commit()

    def load_mapping(self) -> dict[str, dict[str, Any]]:
        if not self.database_url:
            if not self.json_path.exists():
                return {}
            raw = json.loads(self.json_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}

        with self._connect() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT state_key, payload FROM agent_state WHERE namespace = %s",
                    (self.namespace,),
                )
                rows = cur.fetchall()
        result: dict[str, dict[str, Any]] = {}
        for key, payload in rows:
            if isinstance(payload, str):
                payload = json.loads(payload)
            if isinstance(payload, dict):
                result[str(key)] = payload
        return result

    def save_mapping(self, data: dict[str, dict[str, Any]]) -> None:
        if not self.database_url:
            self.json_path.parent.mkdir(parents=True, exist_ok=True)
            self.json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return

        with self._connect() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cur:
                for key, payload in data.items():
                    cur.execute(
                        """
                        INSERT INTO agent_state(namespace, state_key, payload)
                        VALUES (%s, %s, %s::jsonb)
                        ON CONFLICT(namespace, state_key)
                        DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW()
                        """,
                        (self.namespace, key, json.dumps(payload, ensure_ascii=False)),
                    )
            conn.commit()
