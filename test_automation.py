"""
Unit and Negative Integration Tests for automation_service.py.
Adheres to SBMC AGENTS.md Section 5: 80% problem awareness, negative tests & edge cases.
"""

import pytest
from automation_service import (
    LeadAutomationService,
    LeadTier,
    RawLeadInput,
)


@pytest.fixture
def service() -> LeadAutomationService:
    return LeadAutomationService()


# ==========================================
# Positive Tests (Happy Path)
# ==========================================

def test_qualify_enterprise_lead(service: LeadAutomationService):
    """Verifies that leads with budget >= $50,000 are categorized as ENTERPRISE."""
    raw = RawLeadInput(
        lead_id="LEAD-001",
        name="Alice Rahman",
        email="alice@techcorp.io",
        company="TechCorp Solutions",
        budget=75_000.0,
        industry="AI",
    )
    qualified = service.qualify_lead(raw)
    assert qualified.tier == LeadTier.ENTERPRISE
    assert qualified.score == 75  # 60 base + 15 AI industry bonus
    assert "Enterprise budget" in qualified.qualification_notes


def test_qualify_growth_and_standard_leads(service: LeadAutomationService):
    """Tests proper qualification for growth and standard tier leads."""
    growth_raw = RawLeadInput(
        lead_id="LEAD-002",
        name="Karim Khan",
        email="karim@growthstartup.com",
        company="Growth Co",
        budget=20_000.0,
        industry="Retail",
    )
    growth_qualified = service.qualify_lead(growth_raw)
    assert growth_qualified.tier == LeadTier.GROWTH
    assert growth_qualified.score == 40

    std_raw = RawLeadInput(
        lead_id="LEAD-003",
        name="Sadia Ahmed",
        email="sadia@consulting.com",
        company="Consulting Ltd",
        budget=6_000.0,
        industry="Services",
    )
    std_qualified = service.qualify_lead(std_raw)
    assert std_qualified.tier == LeadTier.STANDARD
    assert std_qualified.score == 20


def test_batch_processing_and_summary(service: LeadAutomationService):
    """Verifies batch aggregation metrics, pipeline value, and markdown report."""
    batch = [
        {
            "lead_id": "L-1",
            "name": "CEO John",
            "email": "john@megacorp.com",
            "company": "MegaCorp",
            "budget": 60_000.0,
            "industry": "FinTech",
        },
        {
            "lead_id": "L-2",
            "name": "Jane Dev",
            "email": "jane@smallbiz.org",
            "company": "SmallBiz",
            "budget": 2_000.0,
            "industry": "Education",
        },
    ]
    qualified_leads, summary = service.process_batch(batch)

    assert len(qualified_leads) == 2
    assert summary.total_received == 2
    assert summary.total_valid == 2
    assert summary.total_invalid == 0
    # Pipeline value only includes qualified (L-1 is 60,000, L-2 is unqualified)
    assert summary.total_pipeline_value == 60_000.0
    assert summary.tier_breakdown[LeadTier.ENTERPRISE.value] == 1
    assert summary.tier_breakdown[LeadTier.UNQUALIFIED.value] == 1

    report = service.generate_report(summary)
    assert "Lead Automation Pipeline Summary" in report
    assert "$60,000.00" in report


# ==========================================
# Negative Tests & Edge Cases (AGENTS.md Section 5.2)
# ==========================================

@pytest.mark.parametrize(
    "invalid_email",
    [
        "plainaddress",
        "@missingusername.com",
        "username@.com",
        "username@domain",
        "spaces in@domain.com",
        "",
    ],
)
def test_negative_invalid_emails(invalid_email: str):
    """Asserts that malformed email addresses are rejected with validation errors."""
    with pytest.raises(Exception):
        RawLeadInput(
            lead_id="ERR-1",
            name="Test User",
            email=invalid_email,
            company="Acme Corp",
            budget=10_000.0,
        )


def test_negative_budget_rejection():
    """Asserts that negative budgets violate schema constraints."""
    with pytest.raises(Exception):
        RawLeadInput(
            lead_id="ERR-2",
            name="Negative Budget",
            email="budget@fail.com",
            company="Fail Co",
            budget=-500.0,
        )


def test_negative_whitespace_only_strings():
    """Asserts that whitespace-only names and companies fail validation."""
    with pytest.raises(Exception):
        RawLeadInput(
            lead_id="ERR-3",
            name="   ",
            email="user@example.com",
            company="Real Company",
            budget=5_000.0,
        )

    with pytest.raises(Exception):
        RawLeadInput(
            lead_id="ERR-4",
            name="Valid Name",
            email="user@example.com",
            company="   ",
            budget=5_000.0,
        )


def test_batch_fault_tolerance_with_corrupt_records(service: LeadAutomationService):
    """
    Ensures that invalid records in a batch do not crash the pipeline
    and are captured in the error log while valid records succeed.
    """
    mixed_batch = [
        {
            "lead_id": "OK-1",
            "name": "Good Lead",
            "email": "good@lead.com",
            "company": "Good Company",
            "budget": 25_000.0,
        },
        {
            "lead_id": "BAD-1",
            "name": "Bad Email",
            "email": "not-an-email",
            "company": "Broken Co",
            "budget": 50_000.0,
        },
        {
            # Missing required field 'company' and negative budget
            "lead_id": "BAD-2",
            "name": "Broken Payload",
            "email": "broken@domain.com",
            "budget": -100.0,
        },
        "not_even_a_dictionary",  # Total malformed type
    ]

    qualified_leads, summary = service.process_batch(mixed_batch)

    assert len(qualified_leads) == 1
    assert qualified_leads[0].lead_id == "OK-1"
    assert summary.total_received == 4
    assert summary.total_valid == 1
    assert summary.total_invalid == 3
    assert len(summary.validation_errors) == 3

    # Error details are logged accurately
    assert summary.validation_errors[0]["batch_index"] == 1
    assert "Invalid email format" in summary.validation_errors[0]["error_details"]


# ==========================================
# Boundary Tests
# ==========================================

@pytest.mark.parametrize(
    "budget,expected_tier",
    [
        (0.0, LeadTier.UNQUALIFIED),
        (4_999.99, LeadTier.UNQUALIFIED),
        (5_000.0, LeadTier.STANDARD),
        (14_999.99, LeadTier.STANDARD),
        (15_000.0, LeadTier.GROWTH),
        (49_999.99, LeadTier.GROWTH),
        (50_000.0, LeadTier.ENTERPRISE),
        (1_000_000.0, LeadTier.ENTERPRISE),
    ],
)
def test_tier_budget_boundaries(service: LeadAutomationService, budget: float, expected_tier: LeadTier):
    """Validates exact threshold boundaries for lead tiers."""
    raw = RawLeadInput(
        lead_id=f"BOUND-{budget}",
        name="Boundary Tester",
        email="boundary@test.com",
        company="Boundary Corp",
        budget=budget,
    )
    qualified = service.qualify_lead(raw)
    assert qualified.tier == expected_tier


# ==========================================
# End-to-End Production Workflow Tests (M4)
# ==========================================

def test_vip_alert_dispatch_on_enterprise(service: LeadAutomationService):
    """Verifies that ENTERPRISE leads automatically trigger VIP alert dispatches."""
    batch = [
        {
            "lead_id": "VIP-1",
            "name": "Elon Musk",
            "email": "elon@xcorp.com",
            "company": "X Corp",
            "budget": 150_000.0,
            "industry": "AI",
        },
        {
            "lead_id": "NORM-1",
            "name": "Regular User",
            "email": "reg@user.com",
            "company": "Small Biz",
            "budget": 8_000.0,
            "industry": "Retail",
        },
    ]
    qualified, summary = service.process_batch(batch)

    assert qualified[0].alert_dispatched is True
    assert qualified[1].alert_dispatched is False
    assert len(summary.vip_alerts) == 1
    alert = summary.vip_alerts[0]
    assert alert["lead_id"] == "VIP-1"
    assert alert["company"] == "X Corp"
    assert alert["status"] == "DISPATCHED_SUCCESS"
    assert any("Telegram" in c for c in alert["channels"])


def test_ai_followup_email_generation(service: LeadAutomationService):
    """Ensures tailored email drafts are generated for each qualification tier."""
    raw_enterprise = RawLeadInput(
        lead_id="E-1",
        name="Sarah Jenkins",
        email="sarah@corp.com",
        company="Global Enterprises",
        budget=80_000.0,
        industry="FinTech",
    )
    qualified_e = service.qualify_lead(raw_enterprise)
    assert qualified_e.email_draft is not None
    assert "Strategic AI Architecture" in qualified_e.email_draft
    assert "Sarah Jenkins" in qualified_e.email_draft
    assert "$80,000.00" in qualified_e.email_draft

    raw_growth = RawLeadInput(
        lead_id="G-1",
        name="Alex Rivera",
        email="alex@growthco.net",
        company="GrowthCo",
        budget=20_000.0,
        industry="SaaS",
    )
    qualified_g = service.qualify_lead(raw_growth)
    assert qualified_g.email_draft is not None
    assert "Workflow Automation" in qualified_g.email_draft


def test_export_to_csv_format(service: LeadAutomationService):
    """Verifies RFC 4180 CSV export content and structure."""
    raw = RawLeadInput(
        lead_id="CSV-1",
        name="Farooq Azam",
        email="farooq@azam.org",
        company="Azam Logistics",
        budget=60_000.0,
        industry="Logistics",
    )
    qualified = [service.qualify_lead(raw)]
    csv_content = service.export_to_csv(qualified)

    assert "Lead ID,Name,Email,Company,Industry,Budget (USD),Tier,Score,Qualification Notes,VIP Alert Dispatched,Processed At" in csv_content
    assert "CSV-1,Farooq Azam,farooq@azam.org,Azam Logistics,Logistics,60000.00,ENTERPRISE" in csv_content
    assert "YES" in csv_content


# ==========================================
# Public Customer Ingestion & Webhook Tests
# ==========================================

def test_public_apply_page_renders():
    """Asserts that the public customer quotation portal (/apply) loads cleanly."""
    from fastapi.testclient import TestClient
    from app import app

    client = TestClient(app)
    response = client.get("/apply")
    assert response.status_code == 200
    assert "Request an AI Architecture Consultation" in response.text
    assert "form id=\"applyForm\"" in response.text


def test_public_webhook_enterprise_lead_ingestion():
    """Verifies that public customer submissions are validated and prioritized as VIP."""
    from fastapi.testclient import TestClient
    from app import app

    client = TestClient(app)
    payload = {
        "name": "Tanvir Hossain",
        "email": "tanvir@dhakacloud.ai",
        "company": "Dhaka Cloud AI",
        "budget": 95_000.0,
        "industry": "AI",
        "project_scope": "Full-stack enterprise AI automation",
    }
    response = client.post("/api/webhook/lead", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["tier"] == "ENTERPRISE"
    assert data["is_vip"] is True
    assert data["lead_id"].startswith("PUB-")


def test_public_webhook_invalid_email_rejection():
    """Asserts that invalid public form inputs are rejected with 422 validation errors."""
    from fastapi.testclient import TestClient
    from app import app

    client = TestClient(app)
    payload = {
        "name": "Broken User",
        "email": "not-an-email-domain",
        "company": "Failing Corp",
        "budget": 50_000.0,
        "industry": "General",
        "project_scope": "Testing rejection",
    }
    response = client.post("/api/webhook/lead", json=payload)
    assert response.status_code == 422
    assert "Validation Error" in response.json()["detail"]


