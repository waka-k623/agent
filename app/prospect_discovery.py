from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests

from app.prospect_memory import ProspectMemoryStore


class ProspectDiscovery:
    """Discover Fukui SME candidates, reusing verified bootstrap memory first.

    Discovery never assigns sales scores. If web-search credentials are unavailable,
    the engine still returns verified bootstrap candidates and safely pauses before research.
    """

    SEARCH_URL = "https://api.tavily.com/search"
    BOOTSTRAP_PATH = Path("data/bootstrap_fukui_candidates.json")

    def __init__(self) -> None:
        self.api_key = os.getenv("TAVILY_API_KEY", "").strip()
        self.memory = ProspectMemoryStore()
        self._llm = None
        self._cycle = None

    def _llm_provider(self):
        if self._llm is None:
            from app.providers.factory import get_llm_provider
            self._llm = get_llm_provider()
        return self._llm

    def _research_cycle(self):
        if not self.api_key:
            return None
        if self._cycle is None:
            from app.research_cycle import ResearchCycle
            from app.providers.web_research_provider import TavilyWebResearchProvider
            self._cycle = ResearchCycle(TavilyWebResearchProvider(), memory=self.memory)
        return self._cycle

    def _load_bootstrap(self) -> list[dict[str, Any]]:
        if not self.BOOTSTRAP_PATH.exists():
            return []
        try:
            raw = json.loads(self.BOOTSTRAP_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        candidates = []
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict) or not item.get("company_name"):
                continue
            sources = item.get("discovery_sources") or []
            candidates.append({
                "company_name": str(item["company_name"]).strip(),
                "website": str(item.get("website", "")).strip(),
                "industry": str(item.get("industry", "")).strip(),
                "region": "福井県",
                "discovery_source_url": str(sources[0].get("url", "")) if sources else "",
                "discovery_source_name": str(sources[0].get("name", "bootstrap verified sources")) if sources else "bootstrap verified sources",
                "bootstrap_sources": sources,
                "bootstrap_verified": len(sources) >= 2,
            })
        return candidates

    def _search(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        response = requests.post(
            self.SEARCH_URL,
            json={
                "api_key": self.api_key,
                "query": query,
                "search_depth": "advanced",
                "include_answer": False,
                "include_raw_content": False,
                "max_results": max_results,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("results", [])

    @staticmethod
    def _context(results: list[dict[str, Any]]) -> str:
        return "\n\n".join(
            f"[{i}] {r.get('title','')}\nURL: {r.get('url','')}\n{r.get('content','')}"
            for i, r in enumerate(results, 1)
        )

    def _extract_candidates(self, results: list[dict[str, Any]], industry_hint: str = "") -> list[dict[str, Any]]:
        if not results:
            return []
        system_prompt = (
            "You extract Japanese company candidates from supplied search results. "
            "Return strict JSON only. Do not invent companies, websites, industries, or source URLs."
        )
        user_message = f"""
Goal: find SMEs located in Fukui Prefecture that may be relevant for future AI/DX sales research.
Industry hint: {industry_hint or 'none'}
Date: {date.today().isoformat()}

From ONLY the supplied results, return an array under key "companies".
Each company object must contain company_name, website, industry, region, discovery_source_url, discovery_source_name.
Do not score companies. Do not infer AI readiness.

SEARCH RESULTS:
{self._context(results)}
"""
        raw = self._llm_provider().generate(system_prompt, user_message).strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        companies = data.get("companies", []) if isinstance(data, dict) else []
        allowed_urls = {str(r.get("url", "")) for r in results}
        valid, seen = [], set()
        for item in companies:
            if not isinstance(item, dict):
                continue
            name = str(item.get("company_name", "")).strip()
            source_url = str(item.get("discovery_source_url", "")).strip()
            if not name or source_url not in allowed_urls:
                continue
            key = self.memory.company_key(name, str(item.get("website", "")))
            if key in seen:
                continue
            seen.add(key)
            valid.append({
                "company_name": name,
                "website": str(item.get("website", "")).strip(),
                "industry": str(item.get("industry", "")).strip(),
                "region": "福井県",
                "discovery_source_url": source_url,
                "discovery_source_name": str(item.get("discovery_source_name", "")).strip(),
            })
        return valid

    def discover_candidates(self, *, industry_hint: str = "", max_results: int = 20) -> list[dict[str, Any]]:
        candidates = self._load_bootstrap()
        if self.api_key:
            query = f"福井県 中小企業 {industry_hint} 会社 採用 人手不足 DX デジタル化 業務効率化 企業一覧".strip()
            candidates.extend(self._extract_candidates(self._search(query, max_results=max_results), industry_hint=industry_hint))

        deduped = {}
        for item in candidates:
            if industry_hint and industry_hint not in str(item.get("industry", "")):
                continue
            key = self.memory.company_key(item["company_name"], item.get("website", ""))
            if key not in deduped or item.get("bootstrap_verified"):
                deduped[key] = item
        return list(deduped.values())

    def prioritize_for_research(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranked: list[tuple[int, dict[str, Any]]] = []
        for candidate in candidates:
            existing = self.memory.get(candidate["company_name"], candidate.get("website", ""))
            if existing is None:
                rank, reason = 0, "未調査"
            else:
                plan = self.memory.research_plan(existing)
                mode = plan.get("mode", "")
                if existing.priority in {"P0", "P1"}:
                    rank, reason = 1, "既存の高優先候補を再検証"
                elif mode in {"continue_verification", "refresh_stale_evidence"}:
                    rank, reason = 2, mode
                elif mode == "fill_missing_evidence":
                    rank, reason = 3, "不足根拠を補完"
                else:
                    rank, reason = 4, "記憶再利用・変化確認"
            item = dict(candidate)
            item["research_priority_reason"] = reason
            ranked.append((rank, item))
        ranked.sort(key=lambda x: x[0])
        return [item for _, item in ranked]

    def run(self, *, industry_hint: str = "", research_limit: int = 10) -> dict[str, Any]:
        discovered = self.discover_candidates(industry_hint=industry_hint)
        prioritized = self.prioritize_for_research(discovered)
        selected = prioritized[:research_limit]
        cycle = self._research_cycle()

        if cycle is None:
            researched = []
            blocked_reason = "TAVILY_API_KEY未設定のため、実Web二重検証は未実行"
        else:
            researched = cycle.run_batch([
                {
                    "company_name": c["company_name"],
                    "website": c.get("website", ""),
                    "industry": c.get("industry", ""),
                    "region": "福井県",
                }
                for c in selected
            ]) if selected else []
            blocked_reason = ""

        sales_ready = [r for r in researched if r.get("sales_eligible")]
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "industry_hint": industry_hint,
            "discovered_count": len(discovered),
            "researched_count": len(researched),
            "sales_ready_count": len(sales_ready),
            "blocked_reason": blocked_reason,
            "discovered": prioritized,
            "researched": researched,
            "sales_ready": sales_ready,
        }
