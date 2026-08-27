from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any

import requests

from app.prospect_memory import ProspectMemoryStore
from app.research_cycle import ResearchCycle
from app.providers.web_research_provider import TavilyWebResearchProvider
from app.providers.factory import get_llm_provider


class ProspectDiscovery:
    """Discover Fukui SME candidates from public web evidence, then route them through ResearchCycle.

    Discovery itself never assigns sales scores. It only produces candidate entities with source URLs.
    All sales eligibility is decided later by the two-pass evidence/scoring pipeline.
    """

    SEARCH_URL = "https://api.tavily.com/search"

    def __init__(self) -> None:
        self.api_key = os.environ["TAVILY_API_KEY"]
        self.llm = get_llm_provider()
        self.memory = ProspectMemoryStore()
        self.cycle = ResearchCycle(TavilyWebResearchProvider(), memory=self.memory)

    def _search(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
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
        system_prompt = (
            "You extract Japanese company candidates from supplied search results. "
            "Return strict JSON only. Do not invent companies, websites, industries, or source URLs."
        )
        user_message = f"""
Goal: find SMEs located in Fukui Prefecture that may be relevant for future AI/DX sales research.
Industry hint: {industry_hint or 'none'}
Date: {date.today().isoformat()}

From ONLY the supplied results, return an array under key "companies".
Each company object must contain:
- company_name
- website (official site if directly supported, otherwise empty string)
- industry (only if directly supported, otherwise empty string)
- region (must be 福井県)
- discovery_source_url (must be one of the supplied URLs)
- discovery_source_name

Do not score companies. Do not infer AI readiness. Do not include entities that are not clearly companies/organizations in Fukui Prefecture.

SEARCH RESULTS:
{self._context(results)}
"""
        raw = self.llm.generate(system_prompt, user_message).strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        companies = data.get("companies", []) if isinstance(data, dict) else []
        valid: list[dict[str, Any]] = []
        allowed_urls = {str(r.get("url", "")) for r in results}
        seen: set[str] = set()
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
        query = (
            f"福井県 中小企業 {industry_hint} 会社 採用 人手不足 DX デジタル化 業務効率化 企業一覧"
        ).strip()
        results = self._search(query, max_results=max_results)
        return self._extract_candidates(results, industry_hint=industry_hint)

    def prioritize_for_research(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Prefer unseen, stale, incomplete, or previously promising companies."""
        ranked: list[tuple[int, dict[str, Any]]] = []
        for candidate in candidates:
            existing = self.memory.get(candidate["company_name"], candidate.get("website", ""))
            if existing is None:
                rank = 0
                reason = "未調査"
            else:
                plan = self.memory.research_plan(existing)
                mode = plan.get("mode", "")
                if existing.priority in {"P0", "P1"}:
                    rank = 1
                    reason = "既存の高優先候補を再検証"
                elif mode in {"continue_verification", "refresh_stale_evidence"}:
                    rank = 2
                    reason = mode
                elif mode == "fill_missing_evidence":
                    rank = 3
                    reason = "不足根拠を補完"
                else:
                    rank = 4
                    reason = "記憶再利用・変化確認"
            item = dict(candidate)
            item["research_priority_reason"] = reason
            ranked.append((rank, item))
        ranked.sort(key=lambda x: x[0])
        return [item for _, item in ranked]

    def run(self, *, industry_hint: str = "", research_limit: int = 10) -> dict[str, Any]:
        discovered = self.discover_candidates(industry_hint=industry_hint)
        prioritized = self.prioritize_for_research(discovered)
        selected = prioritized[:research_limit]

        researched = self.cycle.run_batch([
            {
                "company_name": c["company_name"],
                "website": c.get("website", ""),
                "industry": c.get("industry", ""),
                "region": "福井県",
            }
            for c in selected
        ]) if selected else []

        sales_ready = [r for r in researched if r.get("sales_eligible")]
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "industry_hint": industry_hint,
            "discovered_count": len(discovered),
            "researched_count": len(researched),
            "sales_ready_count": len(sales_ready),
            "discovered": prioritized,
            "researched": researched,
            "sales_ready": sales_ready,
        }
