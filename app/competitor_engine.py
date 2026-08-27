from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import requests

from app.providers.factory import get_llm_provider


@dataclass
class CompetitorEvidence:
    competitor_name: str
    website: str = ""
    offering: str = ""
    pricing: str = ""
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    verified_by_two_sources: bool = False


@dataclass
class CompetitivePosition:
    prospect_company: str
    competitors: list[CompetitorEvidence]
    verified_differentiators: list[str]
    risks: list[str]
    recommended_positioning: list[str]
    evidence_gap: list[str]


class CompetitorEngine:
    """Evidence-based competitor research for active sales opportunities.

    Rules:
    - No competitor claim is accepted without a source URL.
    - Pricing remains unknown if public pricing cannot be verified.
    - Pass 2 excludes URLs used in pass 1.
    - Strategy recommendations may summarize verified facts, but may not invent claims.
    """

    SEARCH_URL = "https://api.tavily.com/search"

    def __init__(self) -> None:
        self.api_key = os.environ.get("TAVILY_API_KEY", "")
        self.llm = get_llm_provider()

    def _search(self, query: str, exclude_urls: list[str] | None = None, max_results: int = 8) -> list[dict[str, Any]]:
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
        excluded = set(exclude_urls or [])
        return [r for r in response.json().get("results", []) if r.get("url") not in excluded]

    @staticmethod
    def _context(results: list[dict[str, Any]]) -> str:
        return "\n\n".join(
            f"[{i}] {r.get('title','')}\nURL: {r.get('url','')}\nCONTENT: {r.get('content','')}"
            for i, r in enumerate(results, 1)
        )

    def _extract(self, results: list[dict[str, Any]], prospect_company: str, need: str) -> dict[str, Any]:
        if not results:
            return {"competitors": [], "source_urls": []}
        prompt = {
            "prospect_company": prospect_company,
            "customer_need": need,
            "date": date.today().isoformat(),
            "rules": [
                "Use only supplied search results",
                "Do not invent competitors or pricing",
                "Every non-empty factual field requires a supplied URL",
                "Return unknown pricing as empty string",
            ],
            "required_output": {
                "competitors": [
                    {
                        "competitor_name": "string",
                        "website": "string or empty",
                        "offering": "verified factual summary",
                        "pricing": "verified public pricing or empty",
                        "strengths": ["verified facts only"],
                        "weaknesses": ["only explicit/publicly supported limitations"],
                        "source_urls": ["URLs from supplied results"],
                    }
                ]
            },
            "search_results": self._context(results),
        }
        raw = self.llm.generate(
            "You extract verifiable B2B competitor facts. Return strict JSON only.",
            json.dumps(prompt, ensure_ascii=False),
        ).strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {"competitors": [], "source_urls": []}
        return data if isinstance(data, dict) else {"competitors": [], "source_urls": []}

    @staticmethod
    def _by_name(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            str(item.get("competitor_name", "")).strip().lower(): item
            for item in items
            if isinstance(item, dict) and str(item.get("competitor_name", "")).strip()
        }

    def analyze(self, *, prospect_company: str, industry: str, need: str, our_verified_offer: str) -> CompetitivePosition:
        q1 = f'{industry} {need} AI DX 自動化 サービス 料金 導入 競合'
        pass1_results = self._search(q1)
        p1 = self._extract(pass1_results, prospect_company, need)
        used_urls = list({u for item in p1.get("competitors", []) for u in item.get("source_urls", [])})

        q2 = f'{industry} {need} 業務効率化 システム SaaS 比較 価格 導入事例'
        pass2_results = self._search(q2, exclude_urls=used_urls)
        p2 = self._extract(pass2_results, prospect_company, need)

        first = self._by_name(p1.get("competitors", []))
        second = self._by_name(p2.get("competitors", []))
        verified: list[CompetitorEvidence] = []
        for name in sorted(set(first) | set(second)):
            a, b = first.get(name), second.get(name)
            if not a or not b:
                continue
            urls = list(dict.fromkeys(list(a.get("source_urls", [])) + list(b.get("source_urls", []))))
            if len(set(urls)) < 2:
                continue
            verified.append(
                CompetitorEvidence(
                    competitor_name=str(a.get("competitor_name") or b.get("competitor_name") or ""),
                    website=str(a.get("website") or b.get("website") or ""),
                    offering=str(a.get("offering") or b.get("offering") or ""),
                    pricing=str(a.get("pricing") or b.get("pricing") or ""),
                    strengths=list(dict.fromkeys(list(a.get("strengths", [])) + list(b.get("strengths", [])))),
                    weaknesses=list(dict.fromkeys(list(a.get("weaknesses", [])) + list(b.get("weaknesses", [])))),
                    source_urls=urls,
                    verified_by_two_sources=True,
                )
            )

        facts = [asdict(x) for x in verified]
        strategy_prompt = {
            "prospect_company": prospect_company,
            "customer_need": need,
            "our_verified_offer": our_verified_offer,
            "verified_competitors": facts,
            "instruction": "Compare only supplied verified facts. Do not claim superiority without evidence.",
            "required_output": {
                "verified_differentiators": ["factual difference only"],
                "risks": ["competitive risk supported by facts"],
                "recommended_positioning": ["safe positioning based on verified differences"],
                "evidence_gap": ["facts still needed before making a stronger claim"],
            },
        }
        raw = self.llm.generate(
            "You create conservative B2B competitive positioning from verified facts only. Return strict JSON only.",
            json.dumps(strategy_prompt, ensure_ascii=False),
        ).strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        try:
            strategy = json.loads(raw)
        except json.JSONDecodeError:
            strategy = {}

        return CompetitivePosition(
            prospect_company=prospect_company,
            competitors=verified,
            verified_differentiators=list(strategy.get("verified_differentiators", [])),
            risks=list(strategy.get("risks", [])),
            recommended_positioning=list(strategy.get("recommended_positioning", [])),
            evidence_gap=list(strategy.get("evidence_gap", [])),
        )
