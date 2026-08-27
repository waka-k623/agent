from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.prospect_memory import ProspectMemoryStore
from app.providers.web_research_provider import TavilyWebResearchProvider
from app.prospecting import ProspectScorer


class EvidenceGapResearch:
    """Refresh only missing evidence, then rescore using verified data only."""

    def __init__(self) -> None:
        self.memory = ProspectMemoryStore()
        self.provider = TavilyWebResearchProvider()
        self.scorer = ProspectScorer()

    def run_company(self, company_name: str, website: str = "") -> dict[str, Any]:
        record = self.memory.get(company_name, website)
        if record is None:
            return {"company_name": company_name, "status": "not_found_in_memory"}

        plan = self.memory.research_plan(record)
        missing = list(plan.get("missing_fields") or [])
        if not missing:
            return {
                "company_name": company_name,
                "status": "no_gap",
                "priority": record.priority,
                "score": record.score,
            }

        # Pass 1 targets only the missing fields.
        first = self.provider.research(
            company_name=record.company_name,
            website=record.website,
            industry=record.industry,
            region=record.region,
            research_pass=1,
            existing_sources=record.source_urls,
            missing_fields=missing,
        )
        first_sources = list(dict.fromkeys(record.source_urls + self._sources(first)))

        # Pass 2 excludes pass-1 sources to force independent verification.
        second = self.provider.research(
            company_name=record.company_name,
            website=record.website,
            industry=record.industry,
            region=record.region,
            research_pass=2,
            existing_sources=first_sources,
            missing_fields=missing,
        )

        merged = dict(record.evidence)
        for field in missing:
            m1 = getattr(first, field, None)
            m2 = getattr(second, field, None)
            # We keep a metric only when both passes produced independently sourced evidence.
            if m1 and m2 and m1.usable() and m2.usable() and m1.source_url != m2.source_url:
                merged[field] = asdict(m2)

        record.evidence = merged
        record.source_urls = list(dict.fromkeys(first_sources + self._sources(second)))
        record.research_passes = max(record.research_passes, 2)
        record = self.memory.mark_researched(record)

        # Convert stored evidence back through existing pipeline shape where possible.
        from app.prospecting import EvidenceMetric, ProspectEvidence
        def metric(name: str):
            raw = record.evidence.get(name)
            return EvidenceMetric(**raw) if isinstance(raw, dict) else None

        evidence = ProspectEvidence(
            company_name=record.company_name,
            industry=record.industry,
            region=record.region,
            industry_ai_dx_rate=metric("industry_ai_dx_rate"),
            automation_need=metric("automation_need"),
            company_size_fit=metric("company_size_fit"),
            digital_maturity=metric("digital_maturity"),
            pain_signal=metric("pain_signal"),
            agent_fit=metric("agent_fit"),
            contactability=metric("contactability"),
            evidence_summary=str(record.evidence.get("evidence_summary") or ""),
            research_passes=record.research_passes,
            independent_source_count=len(set(record.source_urls)),
        )
        scored = self.scorer.score(evidence)
        self.memory.mark_scored(
            record,
            score=scored.score,
            priority=scored.priority,
            confidence=scored.confidence,
            exclusion_reason=scored.decision if scored.priority in {"RESEARCH", "P2", "DROP"} else "",
        )

        return {
            "company_name": record.company_name,
            "status": "rescored",
            "missing_before": missing,
            "missing_after": scored.missing_evidence,
            "priority": scored.priority,
            "score": scored.score,
            "confidence": scored.confidence,
            "decision": scored.decision,
        }

    @staticmethod
    def _sources(evidence) -> list[str]:
        urls: list[str] = []
        for field in (
            "industry_ai_dx_rate", "automation_need", "company_size_fit",
            "digital_maturity", "pain_signal", "agent_fit", "contactability"
        ):
            metric = getattr(evidence, field, None)
            if metric and getattr(metric, "source_url", ""):
                urls.append(metric.source_url)
        return urls
