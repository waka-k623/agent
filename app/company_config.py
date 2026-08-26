from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CompanyConfig:
    id: str
    company_name: str
    industry: str = ""
    description: str = ""
    products_services: list[str] = field(default_factory=list)
    ideal_customers: list[str] = field(default_factory=list)
    sales_rules: list[str] = field(default_factory=list)
    qualification_criteria: list[str] = field(default_factory=list)
    tone: str = "professional, concise, friendly"
    forbidden_claims: list[str] = field(default_factory=list)
    approval_policy: dict[str, bool] = field(
        default_factory=lambda: {
            "gmail_draft": True,
            "calendar_event": True,
            "crm_update": True,
        }
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompanyConfig":
        return cls(
            id=str(data["id"]),
            company_name=str(data["company_name"]),
            industry=str(data.get("industry", "")),
            description=str(data.get("description", "")),
            products_services=list(data.get("products_services", [])),
            ideal_customers=list(data.get("ideal_customers", [])),
            sales_rules=list(data.get("sales_rules", [])),
            qualification_criteria=list(data.get("qualification_criteria", [])),
            tone=str(data.get("tone", "professional, concise, friendly")),
            forbidden_claims=list(data.get("forbidden_claims", [])),
            approval_policy=dict(data.get("approval_policy", {})),
        )

    def to_prompt_context(self) -> dict[str, Any]:
        return {
            "company_name": self.company_name,
            "industry": self.industry,
            "description": self.description,
            "products_services": self.products_services,
            "ideal_customers": self.ideal_customers,
            "sales_rules": self.sales_rules,
            "qualification_criteria": self.qualification_criteria,
            "tone": self.tone,
            "forbidden_claims": self.forbidden_claims,
            "approval_policy": self.approval_policy,
        }


class CompanyConfigStore:
    def __init__(self, directory: str = "config/companies") -> None:
        self.directory = Path(directory)

    def list_company_ids(self) -> list[str]:
        if not self.directory.exists():
            return []
        return sorted(path.stem for path in self.directory.glob("*.json"))

    def load(self, company_id: str) -> CompanyConfig:
        path = self.directory / f"{company_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Company config not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return CompanyConfig.from_dict(data)
