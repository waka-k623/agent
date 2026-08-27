from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Optional

from app.company_config import CompanyConfigStore
from app.providers.factory import get_llm_provider


@dataclass
class OutreachPlan:
    company_name: str
    priority: str
    score: Optional[float]
    channel: str
    contact_target: str
    subject: str
    message: str
    value_proposition: str
    evidence_used: list[str]
    source_urls: list[str]
    status: str
    block_reason: str = ""


class OutreachPlanner:
    """Create evidence-grounded outbound plans for P0/P1 prospects only.

    Safety/accuracy rules:
    - Never invent a recipient, email address, decision maker, pain point, or metric.
    - Only use verified prospect evidence and stored source URLs.
    - If a usable contact path is not verified, return blocked/contact_research_required.
    - External sending remains approval-required elsewhere in the system.
    """

    def __init__(self, company_id: str = "default") -> None:
        self.company = CompanyConfigStore().load(company_id)
        self.llm = get_llm_provider()

    @staticmethod
    def _get_memory(item: dict[str, Any]) -> dict[str, Any]:
        return item.get("memory") or item.get("prospect") or item

    @staticmethod
    def _get_score(item: dict[str, Any]) -> dict[str, Any]:
        return item.get("score") or {}

    @staticmethod
    def _verified_evidence(memory: dict[str, Any]) -> tuple[list[str], list[str]]:
        evidence = memory.get("evidence") or {}
        facts: list[str] = []
        urls: list[str] = []
        for key, value in evidence.items():
            if key == "evidence_summary":
                if value:
                    facts.append(str(value))
                continue
            if not isinstance(value, dict):
                continue
            if not value.get("verified"):
                continue
            source_url = str(value.get("source_url") or "").strip()
            source_name = str(value.get("source_name") or "").strip()
            metric_value = value.get("value")
            if source_url and source_name and metric_value is not None:
                facts.append(f"{key}: {metric_value} ({source_name})")
                urls.append(source_url)
        urls.extend(memory.get("source_urls") or [])
        return list(dict.fromkeys(facts)), list(dict.fromkeys(urls))

    @staticmethod
    def _contact_from_memory(memory: dict[str, Any]) -> tuple[str, str]:
        evidence = memory.get("evidence") or {}
        contact = evidence.get("contactability")
        if isinstance(contact, dict) and contact.get("verified") and contact.get("source_url"):
            # We only know a verified contact path exists; do not fabricate an email address.
            return "web_contact", str(contact.get("source_url"))

        for key in ("email", "contact_email"):
            value = str(memory.get(key) or "").strip()
            if value and "@" in value:
                return "email", value

        website = str(memory.get("website") or "").strip()
        if website:
            return "contact_research_required", website
        return "contact_research_required", ""

    def plan(self, item: dict[str, Any]) -> OutreachPlan:
        memory = self._get_memory(item)
        score = self._get_score(item)
        priority = str(score.get("priority") or memory.get("priority") or "")
        company_name = str(memory.get("company_name") or item.get("company") or "").strip()
        numeric_score = score.get("score", memory.get("score"))

        if priority not in {"P0", "P1"}:
            return OutreachPlan(
                company_name=company_name,
                priority=priority or "RESEARCH",
                score=numeric_score,
                channel="none",
                contact_target="",
                subject="",
                message="",
                value_proposition="",
                evidence_used=[],
                source_urls=[],
                status="blocked",
                block_reason="P0/P1ではないため営業対象外",
            )

        facts, source_urls = self._verified_evidence(memory)
        if not facts or len(set(source_urls)) < 2:
            return OutreachPlan(
                company_name=company_name,
                priority=priority,
                score=numeric_score,
                channel="none",
                contact_target="",
                subject="",
                message="",
                value_proposition="",
                evidence_used=facts,
                source_urls=source_urls,
                status="blocked",
                block_reason="営業文面を根拠付ける検証済み情報が不足",
            )

        channel, contact_target = self._contact_from_memory(memory)
        if channel == "contact_research_required":
            return OutreachPlan(
                company_name=company_name,
                priority=priority,
                score=numeric_score,
                channel=channel,
                contact_target=contact_target,
                subject="",
                message="",
                value_proposition="",
                evidence_used=facts,
                source_urls=source_urls,
                status="blocked",
                block_reason="検証済みの接触先が未取得。連絡先追加調査が必要",
            )

        prompt_context = self.company.to_prompt_context()
        system_prompt = (
            "You create Japanese B2B outbound drafts. Use ONLY the verified facts supplied. "
            "Never invent a person, title, email, operational pain, result, case study, statistic, or promise. "
            "Do not claim the target has a problem unless the evidence directly supports it. "
            "Keep the first outreach concise, low-pressure, and specific. Return strict JSON only."
        )
        user_message = json.dumps(
            {
                "seller": prompt_context,
                "prospect": {
                    "company_name": company_name,
                    "industry": memory.get("industry", ""),
                    "region": memory.get("region", ""),
                    "priority": priority,
                    "score": numeric_score,
                    "verified_facts": facts,
                    "source_urls": source_urls,
                },
                "required_output": {
                    "subject": "string",
                    "message": "string",
                    "value_proposition": "string",
                    "evidence_used": ["exact fact labels from verified_facts"],
                },
            },
            ensure_ascii=False,
        )
        raw = self.llm.generate(system_prompt, user_message).strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        try:
            generated = json.loads(raw)
        except json.JSONDecodeError:
            generated = {}

        subject = str(generated.get("subject") or "").strip()
        message = str(generated.get("message") or "").strip()
        value_prop = str(generated.get("value_proposition") or "").strip()
        used = [str(x) for x in generated.get("evidence_used", []) if str(x) in facts]

        if not message or not used:
            return OutreachPlan(
                company_name=company_name,
                priority=priority,
                score=numeric_score,
                channel=channel,
                contact_target=contact_target,
                subject=subject,
                message=message,
                value_proposition=value_prop,
                evidence_used=used,
                source_urls=source_urls,
                status="blocked",
                block_reason="生成文面が検証済み根拠に十分紐づいていない",
            )

        return OutreachPlan(
            company_name=company_name,
            priority=priority,
            score=numeric_score,
            channel=channel,
            contact_target=contact_target,
            subject=subject,
            message=message,
            value_proposition=value_prop,
            evidence_used=used,
            source_urls=source_urls,
            status="ready_for_approval",
        )

    def plan_batch(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        plans = [asdict(self.plan(item)) for item in items]
        order = {"P0": 0, "P1": 1}
        return sorted(plans, key=lambda x: (0 if x["status"] == "ready_for_approval" else 1, order.get(x["priority"], 9), -(x["score"] or 0)))
