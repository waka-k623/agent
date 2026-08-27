from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Protocol

from app.prospect_memory import ProspectMemoryRecord, ProspectMemoryStore
from app.prospecting import EvidenceMetric, ProspectEvidence, ProspectScorer, TwoPassResearchGate


METRIC_NAMES = (
    "industry_ai_dx_rate",
    "automation_need",
    "company_size_fit",
    "digital_maturity",
    "pain_signal",
    "agent_fit",
    "contactability",
)


class ResearchProvider(Protocol):
    """Provider must return real sourced evidence only.

    It must never synthesize missing values. If a metric cannot be verified,
    return None for that metric.
    """

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
        ...


class ResearchCycle:
    """Memory-aware, two-pass research and scoring orchestrator."""

    def __init__(
        self,
        provider: ResearchProvider,
        memory: ProspectMemoryStore | None = None,
        scorer: ProspectScorer | None = None,
    ) -> None:
        self.provider = provider
        self.memory = memory or ProspectMemoryStore()
        self.scorer = scorer or ProspectScorer()

    @staticmethod
    def _metric_to_dict(metric: EvidenceMetric | None) -> dict | None:
        return asdict(metric) if metric is not None else None

    @staticmethod
    def _metric_from_dict(data: dict | None) -> EvidenceMetric | None:
        if not data:
            return None
        return EvidenceMetric(**data)

    def _record_to_evidence(self, record: ProspectMemoryRecord) -> ProspectEvidence:
        kwargs = {
            name: self._metric_from_dict(record.evidence.get(name))
            for name in METRIC_NAMES
        }
        return ProspectEvidence(
            company_name=record.company_name,
            industry=record.industry,
            region=record.region,
            evidence_summary=str(record.evidence.get("evidence_summary", "")),
            research_passes=record.research_passes,
            independent_source_count=len(set(record.source_urls)),
            **kwargs,
        )

    def _merge_pass(self, record: ProspectMemoryRecord, result: ProspectEvidence) -> ProspectMemoryRecord:
        for name in METRIC_NAMES:
            incoming = getattr(result, name)
            if incoming is None or not incoming.usable():
                continue

            current = record.evidence.get(name)
            # Never replace verified evidence with an unverified value.
            if current and bool(current.get("verified")):
                # A later pass may update the value only if it has a source and is verified.
                record.evidence[name] = self._metric_to_dict(incoming)
            else:
                record.evidence[name] = self._metric_to_dict(incoming)

            if incoming.source_url:
                record.source_urls.append(incoming.source_url)

        if result.evidence_summary:
            record.evidence["evidence_summary"] = result.evidence_summary

        record.source_urls = list(dict.fromkeys(record.source_urls))
        record.research_passes = max(record.research_passes, result.research_passes)
        record.last_researched_at = datetime.now().isoformat(timespec="seconds")
        return self.memory.upsert(record)

    def _load_or_create(
        self,
        *,
        company_name: str,
        website: str,
        industry: str,
        region: str,
    ) -> ProspectMemoryRecord:
        existing = self.memory.get(company_name, website)
        if existing:
            if industry and not existing.industry:
                existing.industry = industry
            if region and not existing.region:
                existing.region = region
            return existing

        key = self.memory.company_key(company_name, website)
        return self.memory.upsert(
            ProspectMemoryRecord(
                company_key=key,
                company_name=company_name,
                website=website,
                industry=industry,
                region=region,
            )
        )

    def run_company(
        self,
        *,
        company_name: str,
        website: str = "",
        industry: str = "",
        region: str = "福井県",
    ) -> dict:
        record = self._load_or_create(
            company_name=company_name,
            website=website,
            industry=industry,
            region=region,
        )

        plan = self.memory.research_plan(record)

        # Pass 1: discovery, unless already completed and memory is still reusable.
        if record.research_passes < 1:
            pass1 = self.provider.research(
                company_name=record.company_name,
                website=record.website,
                industry=record.industry,
                region=record.region,
                research_pass=1,
                existing_sources=record.source_urls,
                missing_fields=plan["missing_fields"],
            )
            pass1.research_passes = 1
            record = self._merge_pass(record, pass1)
            plan = self.memory.research_plan(record)

        # Pass 2: independent verification is mandatory before scoring.
        if record.research_passes < 2:
            pass2 = self.provider.research(
                company_name=record.company_name,
                website=record.website,
                industry=record.industry,
                region=record.region,
                research_pass=2,
                existing_sources=record.source_urls,
                missing_fields=plan["missing_fields"],
            )
            pass2.research_passes = 2
            record = self._merge_pass(record, pass2)

        evidence = self._record_to_evidence(record)
        result = self.scorer.score(evidence)

        exclusion_reason = ""
        if result.priority in {"RESEARCH", "P2", "DROP"}:
            exclusion_reason = result.decision

        record = self.memory.mark_scored(
            record,
            score=result.score,
            priority=result.priority,
            confidence=result.confidence,
            exclusion_reason=exclusion_reason,
        )

        return {
            "company": record.company_name,
            "website": record.website,
            "research_plan": self.memory.research_plan(record),
            "score": asdict(result),
            "memory": asdict(record),
            "sales_eligible": result.priority in {"P0", "P1"},
        }

    def run_batch(self, companies: list[dict]) -> list[dict]:
        results = [self.run_company(**company) for company in companies]
        priority_order = {"P0": 0, "P1": 1, "P2": 2, "RESEARCH": 3, "DROP": 4}
        return sorted(
            results,
            key=lambda item: (
                priority_order.get(item["score"]["priority"], 9),
                -(item["score"]["score"] or 0),
            ),
        )
