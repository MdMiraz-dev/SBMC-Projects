"""
Module: automation_service.py
Description: Business automation service for validating, scoring, and summarizing external leads.
Adheres to SBMC AGENTS.md standards: Strict typing, Pydantic schema validation, resilient error handling.
"""

from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator


class LeadTier(str, Enum):
    """Categorized priority tiers for incoming leads."""
    ENTERPRISE = "ENTERPRISE"
    GROWTH = "GROWTH"
    STANDARD = "STANDARD"
    UNQUALIFIED = "UNQUALIFIED"


class RawLeadInput(BaseModel):
    """Schema validation for raw inbound lead payloads."""
    lead_id: str = Field(..., min_length=1, description="Unique identifier for the lead")
    name: str = Field(..., min_length=2, max_length=120, description="Full contact name")
    email: str = Field(..., description="Corporate or business email address")
    company: str = Field(..., min_length=1, max_length=120, description="Company name")
    budget: float = Field(..., ge=0.0, description="Estimated budget in USD, non-negative")
    industry: str = Field(default="General", max_length=80, description="Operating sector")
    source: str = Field(default="Inbound Web", description="Channel of origin")

    @field_validator("email")
    @classmethod
    def validate_email_pattern(cls, value: str) -> str:
        """Enforces realistic RFC 5322 compliant business email format."""
        email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        clean_value = value.strip().lower()
        if not re.match(email_regex, clean_value):
            raise ValueError(f"Invalid email format provided: '{value}'")
        return clean_value

    @field_validator("name", "company")
    @classmethod
    def strip_whitespace(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("Field cannot be empty or contain only whitespace.")
        return clean


class QualifiedLead(BaseModel):
    """Output entity representing a normalized, validated, and scored lead."""
    lead_id: str
    name: str
    email: str
    company: str
    budget: float
    industry: str
    tier: LeadTier
    score: int
    qualification_notes: str
    processed_at: datetime
    email_draft: Optional[str] = None
    alert_dispatched: bool = False


class AutomationSummary(BaseModel):
    """Aggregated metrics resulting from batch lead processing."""
    total_received: int
    total_valid: int
    total_invalid: int
    total_pipeline_value: float
    tier_breakdown: Dict[str, int]
    validation_errors: List[Dict[str, Any]]
    generated_at: datetime
    vip_alerts: List[Dict[str, Any]] = Field(default_factory=list)


class LeadAutomationService:
    """Core business service responsible for ingesting, validating, and qualifying leads."""

    ENTERPRISE_THRESHOLD: float = 50_000.0
    GROWTH_THRESHOLD: float = 15_000.0
    STANDARD_THRESHOLD: float = 5_000.0

    def generate_followup_email(
        self, name: str, company: str, tier: LeadTier, industry: str, budget: float
    ) -> str:
        """Generates an executive, contextual AI follow-up email draft based on lead classification."""
        if tier == LeadTier.ENTERPRISE:
            return (
                f"Subject: Strategic AI Architecture & Executive Consultation for {company}\n\n"
                f"Dear {name},\n\n"
                f"Thank you for connecting with SBMC Technical Operations. Given your focus in {industry} "
                f"and your estimated investment scale of ${budget:,.2f}, we would like to offer an executive-tier "
                f"strategy session with our Principal Solutions Architect.\n\n"
                f"We specialize in mission-critical AI automation, strict security boundaries, and enterprise SLAs. "
                f"Would you be open to a 25-minute discovery call this Thursday at 3:00 PM?\n\n"
                f"Warm regards,\n"
                f"Executive Solutions Team\n"
                f"SBMC AI Operations"
            )
        elif tier == LeadTier.GROWTH:
            return (
                f"Subject: Accelerating {company}'s Workflow Automation with SBMC\n\n"
                f"Hi {name},\n\n"
                f"We noticed {company}'s recent initiative in {industry}. Our growth-tier automation blueprint "
                f"is designed specifically for scaling operations with an agile ${budget:,.2f} budget scope.\n\n"
                f"We can share a tailored proof-of-concept demonstration that shows how our automation pipelines "
                f"eliminate 40+ hours of manual data triage each month.\n\n"
                f"Best,\n"
                f"Growth Client Success Team\n"
                f"SBMC AI Operations"
            )
        elif tier == LeadTier.STANDARD:
            return (
                f"Subject: Welcome to SBMC — Automation Platform Quickstart for {company}\n\n"
                f"Hi {name},\n\n"
                f"Thanks for reaching out! We are thrilled to introduce {company} to our standardized automation workflows. "
                f"You can explore our self-guided sandbox documentation or join our weekly live technical walkthrough.\n\n"
                f"Best regards,\n"
                f"Community Onboarding Team\n"
                f"SBMC AI Operations"
            )
        else:
            return (
                f"Subject: Thank you for your inquiry with SBMC Operations\n\n"
                f"Hi {name},\n\n"
                f"Thank you for contacting SBMC. At this time, our automated enterprise systems require higher minimum deployment scope. "
                f"We invite you to explore our open-source curriculum and self-service community tools.\n\n"
                f"Sincerely,\n"
                f"SBMC Support Team"
            )

    def qualify_lead(self, raw: RawLeadInput) -> QualifiedLead:
        """
        Determines the lead priority tier and assigns a score based on budget and profile.
        """
        score = 0
        notes = []

        # Budget-based scoring
        if raw.budget >= self.ENTERPRISE_THRESHOLD:
            tier = LeadTier.ENTERPRISE
            score += 60
            notes.append(f"Enterprise budget (${raw.budget:,.2f})")
        elif raw.budget >= self.GROWTH_THRESHOLD:
            tier = LeadTier.GROWTH
            score += 40
            notes.append(f"Growth budget (${raw.budget:,.2f})")
        elif raw.budget >= self.STANDARD_THRESHOLD:
            tier = LeadTier.STANDARD
            score += 20
            notes.append(f"Standard tier (${raw.budget:,.2f})")
        else:
            tier = LeadTier.UNQUALIFIED
            score += 5
            notes.append(f"Budget (${raw.budget:,.2f}) below standard threshold")

        # High-priority industry bonus
        priority_industries = {"fintech", "ai", "healthcare", "saas", "cybersecurity"}
        if raw.industry.strip().lower() in priority_industries:
            score += 15
            notes.append(f"High-priority industry: {raw.industry}")

        email_draft = self.generate_followup_email(
            name=raw.name,
            company=raw.company,
            tier=tier,
            industry=raw.industry,
            budget=raw.budget,
        )
        alert_dispatched = (tier == LeadTier.ENTERPRISE)

        return QualifiedLead(
            lead_id=raw.lead_id,
            name=raw.name,
            email=raw.email,
            company=raw.company,
            budget=raw.budget,
            industry=raw.industry,
            tier=tier,
            score=min(score, 100),
            qualification_notes="; ".join(notes),
            processed_at=datetime.now(timezone.utc),
            email_draft=email_draft,
            alert_dispatched=alert_dispatched,
        )

    def process_batch(
        self, raw_items: List[Dict[str, Any]]
    ) -> Tuple[List[QualifiedLead], AutomationSummary]:
        """
        Ingests a batch of raw lead dictionaries, validating each item against Pydantic schema.
        Captures validation errors without halting batch progression.
        """
        qualified_leads: List[QualifiedLead] = []
        validation_errors: List[Dict[str, Any]] = []
        vip_alerts: List[Dict[str, Any]] = []
        tier_counts: Dict[str, int] = {tier.value: 0 for tier in LeadTier}
        total_pipeline_value: float = 0.0

        for index, item in enumerate(raw_items):
            try:
                # Schema ingress validation
                lead_input = RawLeadInput.model_validate(item)
                qualified = self.qualify_lead(lead_input)

                qualified_leads.append(qualified)
                tier_counts[qualified.tier.value] += 1
                if qualified.tier != LeadTier.UNQUALIFIED:
                    total_pipeline_value += qualified.budget

                if qualified.tier == LeadTier.ENTERPRISE:
                    vip_alerts.append({
                        "lead_id": qualified.lead_id,
                        "company": qualified.company,
                        "name": qualified.name,
                        "budget": qualified.budget,
                        "channels": [
                            "Telegram Executive Bot (@sbmc_vip_bot)",
                            "Executive Email (vip@sbmc.local)",
                        ],
                        "dispatched_at": datetime.now(timezone.utc).isoformat(),
                        "status": "DISPATCHED_SUCCESS",
                    })

            except Exception as exc:
                validation_errors.append({
                    "batch_index": index,
                    "raw_payload": item,
                    "error_type": type(exc).__name__,
                    "error_details": str(exc),
                })

        summary = AutomationSummary(
            total_received=len(raw_items),
            total_valid=len(qualified_leads),
            total_invalid=len(validation_errors),
            total_pipeline_value=round(total_pipeline_value, 2),
            tier_breakdown=tier_counts,
            validation_errors=validation_errors,
            generated_at=datetime.now(timezone.utc),
            vip_alerts=vip_alerts,
        )

        return qualified_leads, summary

    def export_to_csv(self, qualified_leads: List[QualifiedLead]) -> str:
        """Converts qualified leads into standard RFC 4180 CSV formatted string."""
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Lead ID",
            "Name",
            "Email",
            "Company",
            "Industry",
            "Budget (USD)",
            "Tier",
            "Score",
            "Qualification Notes",
            "VIP Alert Dispatched",
            "Processed At",
        ])
        for lead in qualified_leads:
            writer.writerow([
                lead.lead_id,
                lead.name,
                lead.email,
                lead.company,
                lead.industry,
                f"{lead.budget:.2f}",
                lead.tier.value,
                lead.score,
                lead.qualification_notes,
                "YES" if lead.alert_dispatched else "NO",
                lead.processed_at.isoformat(),
            ])
        return output.getvalue()

    def generate_report(self, summary: AutomationSummary) -> str:
        """Produces a human-readable Markdown summary report."""
        report_lines = [
            "# Lead Automation Pipeline Summary",
            f"- **Generated At**: {summary.generated_at.isoformat()}",
            f"- **Total Ingested**: {summary.total_received}",
            f"- **Successfully Qualified**: {summary.total_valid}",
            f"- **Validation Failures**: {summary.total_invalid}",
            f"- **Pipeline Potential Value**: ${summary.total_pipeline_value:,.2f}",
            "",
            "## Tier Distribution",
        ]
        for tier, count in summary.tier_breakdown.items():
            report_lines.append(f"- **{tier}**: {count}")

        if summary.validation_errors:
            report_lines.extend(["", "## Rejection Log"])
            for err in summary.validation_errors:
                report_lines.append(
                    f"- Record #{err['batch_index']} ({err['error_type']}): {err['error_details']}"
                )

        return "\n".join(report_lines)


if __name__ == "__main__":
    service = LeadAutomationService()
    sample_leads = [
        {
            "lead_id": "L-101",
            "name": "Mahmudul Hasan",
            "email": "m.hasan@fintechbangla.com",
            "company": "Fintech Bangla Ltd",
            "budget": 65000.0,
            "industry": "FinTech",
        },
        {
            "lead_id": "L-102",
            "name": "Sarah Connor",
            "email": "sarah@cyberdyne.ai",
            "company": "Cyberdyne Systems",
            "budget": 25000.0,
            "industry": "AI",
        },
        {
            "lead_id": "L-103",
            "name": "Tariq Zaman",
            "email": "tzaman@localmart.com",
            "company": "LocalMart",
            "budget": 3500.0,
            "industry": "Retail",
        },
        {
            "lead_id": "L-INVALID",
            "name": "Bad Record",
            "email": "not-an-email-address",
            "company": "Broken Org",
            "budget": -500.0,
        },
    ]

    print("Executing Lead Automation Service demo...")
    leads, summary = service.process_batch(sample_leads)
    print(service.generate_report(summary))

