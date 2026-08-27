from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

import requests

from app.prospecting import EvidenceMetric, ProspectEvidence
from app.providers.factory import get_llm_provider


class TavilyWebResearchProvider:
    """Real web research provider using Tavily search + factual extraction.

    The LLM extracts facts only. All 0..1 prospect metrics are produced by explicit,
    deterministic rules below so the model cannot invent a subjective score.
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
            "You are a factual evidence extractor for B2B prospect research. "
            "Use ONLY the supplied search results. Never infer, estimate, or invent a number. "
            "Extract observable facts and exact source URLs only. Return strict JSON only."
        )
        user_message = f"""
Company: {company_name}
Industry: {industry}
Region: {region}
Research pass: {research_pass}
Date: {date.today().isoformat()}

Return only facts directly supported by the search results using this schema:
{{
  "industry_ai_dx_rate": {{"value": number|null, "source_url": "", "source_name": ""}},
  "employee_count": {{"value": number|null, "source_url": "", "source_name": ""}},
  "manual_workflow_signals": [{{"label": "paper/manual data entry/reporting/photo-document handling/scheduling/inquiry handling/other", "source_url": "", "source_name": ""}}],
  "digital_tool_signals": [{{"label": "cloud/SaaS/CRM/digital form/DX project/AI/other", "source_url": "", "source_name": ""}}],
  "pain_signals": [{{"label": "hiring shortage/continuous recruitment/workload/overtime/efficiency issue/growth pressure/other", "source_url": "", "source_name": ""}}],
  "recurring_information_workflows": [{{"label": "inquiries/scheduling/document processing/reporting/sales follow-up/customer support/other", "source_url": "", "source_name": ""}}],
  "contact_paths": [{{"type": "email/form/phone", "value": "exact visible value or URL", "source_url": "", "source_name": ""}}],
  "evidence_summary": "concise Japanese summary of verified facts only",
  "source_urls": []
}}

Rules:
- Do not output any 0..1 score.
- Do not infer a pain point from industry stereotypes.
- Keep employee_count null unless an explicit number is present.
- Keep industry_ai_dx_rate null unless an explicit percentage from a credible statistic is present.
- Use exact URLs from supplied search results only.
- Do not repeat the same fact as multiple signals.

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
    def _direct_metric(data: Any) -> EvidenceMetric | None:
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
        return EvidenceMetric(value=value, source_url=source_url, source_name=source_name, observed_at=date.today().isoformat(), verified=True)

    @staticmethod
    def _signal_metric(signals: Any, *, denominator: int = 3) -> EvidenceMetric | None:
        if not isinstance(signals, list):
            return None
        valid = []
        seen = set()
        for item in signals:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip().lower()
            url = str(item.get("source_url") or "").strip()
            name = str(item.get("source_name") or "").strip()
            key = (label, url)
            if label and url and name and key not in seen:
                seen.add(key)
                valid.append((label, url, name))
        if not valid:
            return None
        value = min(len(valid) / float(denominator), 1.0)
        first = valid[0]
        return EvidenceMetric(value=value, source_url=first[1], source_name=first[2], observed_at=date.today().isoformat(), verified=True)

    @staticmethod
    def _company_size_metric(employee_data: Any) -> EvidenceMetric | None:
        metric = TavilyWebResearchProvider._direct_metric(employee_data)
        if metric is None:
            return None
        employees = metric.value
        # Transparent sales-fit heuristic, not a legal SME classification.
        if 5 <= employees <= 300:
            fit = 1.0
        elif 301 <= employees <= 500:
            fit = 0.5
        else:
            fit = 0.0
        metric.value = fit
        return metric

    @staticmethod
    def _contact_metric(paths: Any) -> EvidenceMetric | None:
        if not isinstance(paths, list):
            return None
        rank = {"email": 1.0, "form": 0.8, "phone": 0.6}
        best = None
        for item in paths:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type") or "").strip().lower()
            source_url = str(item.get("source_url") or "").strip()
            source_name = str(item.get("source_name") or "").strip()
            if kind in rank and source_url and source_name:
                candidate = (rank[kind], source_url, source_name)
                if best is None or candidate[0] > best[0]:
                    best = candidate
        if best is None:
            return None
        return EvidenceMetric(value=best[0], source_url=best[1], source_name=best[2], observed_at=date.today().isoformat(), verified=True)

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
            query = f'"{company_name}" {region} {industry} 会社 従業員 採用 DX IT 業務効率化 AI 導入率 業界 統計 中小企業'
            excludes: list[str] = []
        else:
            query = f'"{company_name}" {region} {industry} 公式 求人 統計 人手不足 DX デジタル化 AI 活用 公的資料'
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
            industry_ai_dx_rate=self._direct_metric(extracted.get("industry_ai_dx_rate")),
            automation_need=self._signal_metric(extracted.get("manual_workflow_signals")),
            company_size_fit=self._company_size_metric(extracted.get("employee_count")),
            digital_maturity=self._signal_metric(extracted.get("digital_tool_signals")),
            pain_signal=self._signal_metric(extracted.get("pain_signals")),
            agent_fit=self._signal_metric(extracted.get("recurring_information_workflows")),
            contactability=self._contact_metric(extracted.get("contact_paths")),
            evidence_summary=str(extracted.get("evidence_summary", "")),
            research_passes=research_pass,
            independent_source_count=len(set(extracted.get("source_urls", []))),
        )
