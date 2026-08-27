from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

import requests

from app.prospecting import EvidenceMetric, ProspectEvidence
from app.providers.factory import get_llm_provider


class TavilyWebResearchProvider:
    """Real web research provider using Tavily search + LLM extraction.

    Rules:
    - Never invent missing values.
    - Every metric requires a source URL/name.
    - Pass 2 attempts independent verification using different search results.
    - Unknown/unverifiable metrics remain None.
    """

    SEARCH_URL = "https://api.tavily.com/search"

    def __init__(self) -> None:
        self.api_key = os.environ["TAVILY_API_KEY"]
        self.llm = get_llm_provider()

    def _search(self, query: str, *, exclude_urls: list[str] | None = None, max_results: int = 8) -> list[dict[str, Any]]:
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "advanced",
            "include_answer": False,
            "include_raw_content": False,
            "max_results": max_results,
        }
        response = requests.post(self.SEARCH_URL, json=payload, timeout=30)
        response.raise_for_status()
        results = response.json().get("results", [])
        excluded = set(exclude_urls or [])
        return [r for r in results if r.get("url") not in excluded]

    @staticmethod
    def _result_context(results: list[dict[str, Any]]) -> str:
        chunks = []
        for idx, r in enumerate(results, 1):
            chunks.append(
                f"[{idx}] TITLE: {r.get('title','')}\nURL: {r.get('url','')}\nCONTENT: {r.get('content','')}"
            )
        return "\n\n".join(chunks)

    def _extract(self, *, company_name: str, industry: str, region: str, research_pass: int, results: list[dict[str, Any]]) -> dict[str, Any]:
        system_prompt = (
            "You are an evidence extraction engine for B2B prospect research. "
            "Use ONLY the supplied search results. Never infer or invent numeric values. "
            "If a metric cannot be directly supported, return null. "
            "Return strict JSON only."
        )
        user_message = f"""
Company: {company_name}
Industry: {industry}
Region: {region}
Research pass: {research_pass}
Date: {date.today().isoformat()}

Extract these fields ONLY when directly supported by the supplied sources:
- industry_ai_dx_rate: percentage 0-100 from credible industry/public statistics
- automation_need: 0-1 only if source evidence clearly supports repetitive/manual workload intensity
- company_size_fit: 0-1 only if company size is explicitly available and can be mapped to SME fit
- digital_maturity: 0-1 only if explicit digital/cloud/DX adoption evidence exists
- pain_signal: 0-1 only if explicit hiring shortage, workload, growth, efficiency, or operational pain exists
- agent_fit: 0-1 only if recurring information-processing/workflow tasks are explicitly evidenced
- contactability: 0-1 only if a usable business contact path is explicitly shown

For every non-null metric return:
{{
  "value": number,
  "source_url": "exact source URL from supplied results",
  "source_name": "source title/publisher",
  "observed_at": "YYYY-MM-DD"
}}

Also return:
- evidence_summary: concise Japanese summary of verified facts only
- source_urls: unique list of URLs actually used

Do not average, estimate, or fill gaps.

SEARCH RESULTS:
{self._result_context(results)}
"""
        raw = self.llm.generate(system_prompt, user_message).strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {"evidence_summary": "", "source_urls": []}
        return data if isinstance(data, dict) else {"evidence_summary": "", "source_urls": []}

    @staticmethod
    def _metric(data: Any) -> EvidenceMetric | None:
        if not isinstance(data, dict) or data.get("value") is None:
            return None
        try:
            value = float(data["value"])
        except (TypeError, ValueError):
            return None
        source_url = str(data.get("source_url", "")).strip()
        source_name = str(data.get("source_name", "")).strip()
        if not source_url or not source_name:
            return None
        return EvidenceMetric(
            value=value,
            source_url=source_url,
            source_name=source_name,
            observed_at=str(data.get("observed_at") or date.today().isoformat()),
            verified=True,
        )

    def research(
        self,
        *,
        company_name: str,
        website: str,
        industry: str,
        region: str,
        research_pass: int,
        existing_sources: list[str],
        missing_fields: list[str],
    ) -> ProspectEvidence:
        if research_pass == 1:
            query = (
                f'"{company_name}" {region} {industry} 会社 従業員 採用 DX IT 業務効率化 '
                f'AI 導入率 業界 統計 中小企業'
            )
            excludes: list[str] = []
        else:
            query = (
                f'"{company_name}" {region} {industry} 公式 求人 統計 人手不足 DX デジタル化 '
                f'AI 活用 公的資料'
            )
            excludes = existing_sources

        results = self._search(query, exclude_urls=excludes)
        extracted = self._extract(
            company_name=company_name,
            industry=industry,
            region=region,
            research_pass=research_pass,
            results=results,
        )

        return ProspectEvidence(
            company_name=company_name,
            industry=industry,
            region=region,
            industry_ai_dx_rate=self._metric(extracted.get("industry_ai_dx_rate")),
            automation_need=self._metric(extracted.get("automation_need")),
            company_size_fit=self._metric(extracted.get("company_size_fit")),
            digital_maturity=self._metric(extracted.get("digital_maturity")),
            pain_signal=self._metric(extracted.get("pain_signal")),
            agent_fit=self._metric(extracted.get("agent_fit")),
            contactability=self._metric(extracted.get("contactability")),
            evidence_summary=str(extracted.get("evidence_summary", "")),
            research_passes=research_pass,
            independent_source_count=len(set(extracted.get("source_urls", []))),
        )
