"""
Module: app.py
Description: FastAPI web application for SBMC Lead Automation Engine.
Features:
- Operations Dashboard (/) with live metrics, VIP alerts, AI email drafts, and CSV export.
- Public Customer Quotation & Lead Form (/apply).
- Real-time Webhook API (/api/webhook/lead) with live state synchronization.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List
import uuid

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

from automation_service import LeadAutomationService, LeadTier, RawLeadInput

app = FastAPI(
    title="SBMC Lead Automation & Public Quotation System",
    description="Full-stack AI Operations Lead Qualification System with Public Ingestion and Webhooks",
    version="2.0.0",
)

service = LeadAutomationService()

INITIAL_SAMPLE_DATA: List[Dict[str, Any]] = [
    {
        "lead_id": "LD-901",
        "name": "Dr. Tariq Rahman",
        "email": "trahman@apexai.cloud",
        "company": "Apex AI Systems",
        "budget": 125000.0,
        "industry": "AI",
        "source": "Inbound Enterprise Portal",
    },
    {
        "lead_id": "LD-902",
        "name": "Nusrat Jahan",
        "email": "nusrat@dhakafintech.com",
        "company": "Dhaka FinTech Global",
        "budget": 65000.0,
        "industry": "FinTech",
        "source": "Webinar Lead",
    },
    {
        "lead_id": "LD-903",
        "name": "Farhan Chowdhury",
        "email": "farhan@greengrid.org",
        "company": "GreenGrid Energy",
        "budget": 24000.0,
        "industry": "CleanTech",
        "source": "LinkedIn Campaign",
    },
    {
        "lead_id": "LD-904",
        "name": "Ayesha Siddiqua",
        "email": "ayesha@novastudio.design",
        "company": "Nova Creative Studio",
        "budget": 8500.0,
        "industry": "Design & Media",
        "source": "Direct Contact",
    },
    {
        "lead_id": "LD-905",
        "name": "Kamrul Islam",
        "email": "kamrul@microblog.xyz",
        "company": "MicroBlog Tech",
        "budget": 1500.0,
        "industry": "Blogging",
        "source": "Organic Search",
    },
]

# In-memory synchronized live queue for real-time customer submissions
LIVE_LEADS_STORE: List[Dict[str, Any]] = list(INITIAL_SAMPLE_DATA)


class ProcessLeadsRequest(BaseModel):
    leads: List[Dict[str, Any]]


class PublicWebhookPayload(BaseModel):
    name: str
    email: str
    company: str
    budget: float
    industry: str = "General"
    project_scope: str = "Standard consultation request"


# ==============================================================================
# API Endpoints
# ==============================================================================

@app.get("/api/sample-leads")
def get_sample_leads() -> List[Dict[str, Any]]:
    """Returns baseline curated sample leads."""
    return INITIAL_SAMPLE_DATA


@app.get("/api/live-status")
def get_live_status() -> Dict[str, Any]:
    """Returns the latest processed state of all live leads for real-time dashboard polling."""
    qualified_leads, summary = service.process_batch(LIVE_LEADS_STORE)
    return {
        "raw_queue": LIVE_LEADS_STORE,
        "leads": [lead.model_dump() for lead in qualified_leads],
        "summary": summary.model_dump(),
    }


@app.post("/api/webhook/lead")
def ingest_public_webhook(payload: PublicWebhookPayload) -> Dict[str, Any]:
    """
    Public webhook endpoint that receives customer inquiries, validates inputs,
    qualifies priority tier, and immediately feeds into the live dashboard queue.
    """
    generated_id = f"PUB-{uuid.uuid4().hex[:6].upper()}"

    try:
        raw_lead = RawLeadInput(
            lead_id=generated_id,
            name=payload.name,
            email=payload.email,
            company=payload.company,
            budget=payload.budget,
            industry=payload.industry,
            source="Public Webhook (/apply)",
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Validation Error: {str(exc)}")

    qualified = service.qualify_lead(raw_lead)

    # Prepend to live store so it appears at top of dashboard
    item_dict = raw_lead.model_dump()
    LIVE_LEADS_STORE.insert(0, item_dict)

    return {
        "status": "success",
        "message": "Lead ingested, validated, and prioritized successfully.",
        "lead_id": qualified.lead_id,
        "tier": qualified.tier.value,
        "score": qualified.score,
        "is_vip": qualified.tier == LeadTier.ENTERPRISE,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/process-leads")
def process_leads(payload: ProcessLeadsRequest) -> Dict[str, Any]:
    """Ingests and validates raw batch of leads."""
    if not payload.leads:
        raise HTTPException(status_code=400, detail="Leads list cannot be empty.")

    qualified_leads, summary = service.process_batch(payload.leads)
    return {
        "leads": [lead.model_dump() for lead in qualified_leads],
        "summary": summary.model_dump(),
    }


@app.post("/api/export-csv")
def export_leads_csv(payload: ProcessLeadsRequest) -> Response:
    """Exports validated leads to downloadable RFC 4180 CSV format."""
    if not payload.leads:
        raise HTTPException(status_code=400, detail="No leads provided for export.")

    qualified_leads, _ = service.process_batch(payload.leads)
    csv_content = service.export_to_csv(qualified_leads)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=qualified_leads.csv"},
    )


# ==============================================================================
# Public Customer Quotation Form Page (/apply)
# ==============================================================================

@app.get("/apply", response_class=HTMLResponse)
def public_apply_page() -> str:
    """Renders the client-facing public quotation and lead intake portal."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Enterprise AI Solutions & Consultation | SBMC Operations</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>body { font-family: 'Plus Jakarta Sans', sans-serif; }</style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen antialiased selection:bg-indigo-500 selection:text-white">
    <!-- Top Branding Header -->
    <header class="border-b border-slate-800/80 bg-slate-900/60 backdrop-blur sticky top-0 z-40">
        <div class="max-w-5xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
                    <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                </div>
                <div>
                    <span class="font-bold text-white text-base">SBMC Enterprise AI</span>
                    <span class="text-xs text-indigo-400 block -mt-1 font-medium">Technical Solutions Consultation</span>
                </div>
            </div>
            <div class="flex items-center gap-3">
                <a href="/" class="px-3.5 py-1.5 rounded-lg border border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-xs font-semibold text-slate-300 transition flex items-center gap-1.5">
                    <span>Operations Dashboard</span>
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/></svg>
                </a>
            </div>
        </div>
    </header>

    <main class="max-w-3xl mx-auto px-4 sm:px-6 py-12 space-y-8">
        <!-- Hero Title -->
        <div class="text-center space-y-3">
            <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                <span class="w-2 h-2 rounded-full bg-indigo-400 animate-pulse"></span>
                Instant Qualification & Direct Executive Routing
            </div>
            <h1 class="text-3xl sm:text-4xl font-extrabold text-white tracking-tight">
                Request an AI Architecture Consultation
            </h1>
            <p class="text-sm sm:text-base text-slate-400 max-w-xl mx-auto">
                Tell us about your organization's goals. Our automated engine evaluates your scope instantly, prioritizing enterprise requests with customized SLAs.
            </p>
        </div>

        <!-- Intake Form Container -->
        <div class="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 sm:p-10 shadow-2xl relative">
            <form id="applyForm" onsubmit="submitPublicLead(event)" class="space-y-6">
                <!-- Two Column Inputs -->
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-5">
                    <div>
                        <label class="block text-xs font-bold uppercase tracking-wider text-slate-300 mb-2">Your Full Name *</label>
                        <input type="text" id="custName" required placeholder="e.g. Mahir Faisal" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition">
                    </div>
                    <div>
                        <label class="block text-xs font-bold uppercase tracking-wider text-slate-300 mb-2">Corporate Email *</label>
                        <input type="email" id="custEmail" required placeholder="e.g. mahir@techscale.io" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition">
                    </div>
                </div>

                <div class="grid grid-cols-1 sm:grid-cols-2 gap-5">
                    <div>
                        <label class="block text-xs font-bold uppercase tracking-wider text-slate-300 mb-2">Company / Organization *</label>
                        <input type="text" id="custCompany" required placeholder="e.g. TechScale Solutions" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition">
                    </div>
                    <div>
                        <label class="block text-xs font-bold uppercase tracking-wider text-slate-300 mb-2">Operating Sector *</label>
                        <select id="custIndustry" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition">
                            <option value="AI">Artificial Intelligence & ML</option>
                            <option value="FinTech">FinTech & Banking</option>
                            <option value="Healthcare">Healthcare & Biotech</option>
                            <option value="SaaS">Enterprise SaaS</option>
                            <option value="Cybersecurity">Cybersecurity</option>
                            <option value="E-Commerce">E-Commerce & Retail</option>
                            <option value="Logistics">Supply Chain & Logistics</option>
                            <option value="General">General Commercial</option>
                        </select>
                    </div>
                </div>

                <!-- Budget Selection with Quick Buttons -->
                <div>
                    <div class="flex items-center justify-between mb-2">
                        <label class="block text-xs font-bold uppercase tracking-wider text-slate-300">Estimated Project Budget ($ USD) *</label>
                        <span class="text-xs text-indigo-400">Enterprise tier starts at $50k+</span>
                    </div>
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
                        <button type="button" onclick="setBudget(15000)" class="py-2 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-800 text-xs font-semibold text-slate-300 transition">$15,000</button>
                        <button type="button" onclick="setBudget(35000)" class="py-2 rounded-lg bg-slate-950 hover:bg-slate-800 border border-slate-800 text-xs font-semibold text-slate-300 transition">$35,000</button>
                        <button type="button" onclick="setBudget(75000)" class="py-2 rounded-lg bg-indigo-950/60 hover:bg-indigo-900/60 border border-indigo-500/40 text-xs font-bold text-indigo-300 transition">⭐ $75,000 (VIP)</button>
                        <button type="button" onclick="setBudget(150000)" class="py-2 rounded-lg bg-purple-950/60 hover:bg-purple-900/60 border border-purple-500/40 text-xs font-bold text-purple-300 transition">⭐ $150,000 (VIP)</button>
                    </div>
                    <input type="number" id="custBudget" step="500" min="0" required placeholder="Enter exact amount (e.g. 85000)" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition font-mono">
                </div>

                <!-- Scope / Requirements -->
                <div>
                    <label class="block text-xs font-bold uppercase tracking-wider text-slate-300 mb-2">Project Scope & Automation Objectives</label>
                    <textarea id="custScope" rows="3" placeholder="Briefly describe what automated systems or integrations your team needs..." class="w-full bg-slate-950 border border-slate-800 rounded-xl p-4 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition"></textarea>
                </div>

                <!-- Submit Button -->
                <button type="submit" id="submitBtn" class="w-full py-4 rounded-2xl bg-gradient-to-r from-indigo-500 via-violet-600 to-indigo-600 hover:from-indigo-600 hover:to-violet-700 text-white font-bold text-base shadow-xl shadow-indigo-500/25 transition flex items-center justify-center gap-2">
                    <span>Submit Consultation Request</span>
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/></svg>
                </button>
            </form>

            <!-- Success State Overlay (Hidden by Default) -->
            <div id="successCard" class="hidden text-center py-8 space-y-5">
                <div class="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center mx-auto text-3xl">
                    ✅
                </div>
                <div class="space-y-2">
                    <h2 class="text-2xl font-bold text-white">Consultation Request Received!</h2>
                    <p class="text-sm text-slate-400 max-w-md mx-auto" id="successSubtitle">
                        Your inquiry has been processed by our automated scoring engine.
                    </p>
                </div>

                <div class="bg-slate-950 border border-slate-800 rounded-2xl p-5 max-w-md mx-auto text-left space-y-2 font-mono text-xs">
                    <div class="flex justify-between border-b border-slate-800 pb-2">
                        <span class="text-slate-500">Tracking Reference:</span>
                        <span id="resLeadId" class="text-indigo-400 font-bold"></span>
                    </div>
                    <div class="flex justify-between border-b border-slate-800 pb-2">
                        <span class="text-slate-500">Qualification Priority:</span>
                        <span id="resTierBadge"></span>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-slate-500">Internal Routing:</span>
                        <span id="resRouting" class="text-emerald-400 font-semibold">Live Webhook Ingested</span>
                    </div>
                </div>

                <div class="flex flex-col sm:flex-row items-center justify-center gap-3 pt-3">
                    <button onclick="resetApplyForm()" class="px-5 py-2.5 rounded-xl border border-slate-700 bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 transition">
                        Submit Another Request
                    </button>
                    <a href="/" class="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-xs font-bold text-white shadow-lg shadow-indigo-600/20 transition flex items-center gap-1.5">
                        <span>View Operations Dashboard</span>
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/></svg>
                    </a>
                </div>
            </div>
        </div>
    </main>

    <script>
        function setBudget(amount) {
            document.getElementById('custBudget').value = amount;
        }

        async function submitPublicLead(e) {
            e.preventDefault();
            const btn = document.getElementById('submitBtn');
            btn.disabled = true;
            btn.innerText = 'Processing with Automation Engine...';

            const payload = {
                name: document.getElementById('custName').value.trim(),
                email: document.getElementById('custEmail').value.trim(),
                company: document.getElementById('custCompany').value.trim(),
                industry: document.getElementById('custIndustry').value,
                budget: parseFloat(document.getElementById('custBudget').value),
                project_scope: document.getElementById('custScope').value.trim() || 'General AI Operations Consultation'
            };

            try {
                const res = await fetch('/api/webhook/lead', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Failed to submit consultation request');
                }

                const data = await res.json();
                showSuccess(data);
            } catch (err) {
                alert('Submission Error: ' + err.message);
                btn.disabled = false;
                btn.innerText = 'Submit Consultation Request';
            }
        }

        function showSuccess(data) {
            document.getElementById('applyForm').classList.add('hidden');
            const successCard = document.getElementById('successCard');
            successCard.classList.remove('hidden');

            document.getElementById('resLeadId').innerText = data.lead_id;

            let badgeHtml = '';
            if (data.tier === 'ENTERPRISE') {
                badgeHtml = '<span class="px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/40 text-[11px] font-bold">⭐ VIP Enterprise (Priority SLA)</span>';
                document.getElementById('resRouting').innerText = 'Dispatched to Telegram VIP Bot';
            } else if (data.tier === 'GROWTH') {
                badgeHtml = '<span class="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[11px] font-semibold">🚀 Growth Tier</span>';
            } else if (data.tier === 'STANDARD') {
                badgeHtml = '<span class="px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/40 text-[11px]">💼 Standard</span>';
            } else {
                badgeHtml = '<span class="px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 text-[11px]">⚪ Unqualified</span>';
            }
            document.getElementById('resTierBadge').innerHTML = badgeHtml;
        }

        function resetApplyForm() {
            document.getElementById('applyForm').reset();
            document.getElementById('applyForm').classList.remove('hidden');
            document.getElementById('successCard').classList.add('hidden');
            document.getElementById('submitBtn').disabled = false;
            document.getElementById('submitBtn').innerText = 'Submit Consultation Request';
        }
    </script>
</body>
</html>
"""


# ==============================================================================
# Operations Dashboard UI (/)
# ==============================================================================

@app.get("/", response_class=HTMLResponse)
def dashboard_ui() -> str:
    """Renders the comprehensive, modern dashboard HTML user interface with real-time polling."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SBMC Lead Automation Dashboard — Production Edition</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>body { font-family: 'Plus Jakarta Sans', sans-serif; }</style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen">
    <!-- Top Navigation -->
    <header class="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-40">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
                    <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                </div>
                <div>
                    <h1 class="font-bold text-lg text-white leading-tight">SBMC Automation Engine</h1>
                    <p class="text-xs text-slate-400">Production Workflow • VIP Alert Dispatch • Real-time Webhooks</p>
                </div>
            </div>
            <div class="flex items-center gap-3">
                <a href="/apply" target="_blank" class="px-3 py-1.5 rounded-lg border border-indigo-500/30 bg-indigo-600/15 hover:bg-indigo-600/25 text-xs font-bold text-indigo-300 transition flex items-center gap-1.5">
                    <span>🌐 Public Customer Form (/apply)</span>
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
                </a>
                <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                    Live Webhook Ingestion
                </span>
                <a href="/docs" target="_blank" class="text-xs text-slate-400 hover:text-white transition">Docs &rarr;</a>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        <!-- Live VIP Alert Dispatch Banner (Appears when VIPs detected) -->
        <div id="vipAlertBanner" class="hidden bg-gradient-to-r from-purple-950/80 via-indigo-950/60 to-purple-950/80 border border-purple-500/40 rounded-2xl p-5 shadow-2xl relative overflow-hidden transition-all">
            <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div class="flex items-start gap-3">
                    <div class="w-10 h-10 rounded-xl bg-purple-500/20 border border-purple-500/30 flex items-center justify-center flex-shrink-0 animate-bounce">
                        <span class="text-xl">🔔</span>
                    </div>
                    <div>
                        <div class="flex items-center gap-2">
                            <span class="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-purple-500 text-white uppercase tracking-wider">
                                Live VIP Dispatch
                            </span>
                            <span class="text-xs text-purple-300">Telegram Bot & Executive Email Active</span>
                        </div>
                        <h3 class="text-base font-bold text-white mt-1">High-Value Enterprise Accounts Detected</h3>
                        <p class="text-xs text-slate-300 mt-0.5">Real-time alerts dispatched to Telegram Executive Channel (@sbmc_vip_bot) and Executive Email.</p>
                    </div>
                </div>
                <div id="vipAlertBadges" class="flex flex-wrap items-center gap-2"></div>
            </div>
        </div>

        <!-- Control Actions Banner -->
        <div class="bg-gradient-to-r from-slate-900 via-indigo-950/30 to-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col md:flex-row items-center justify-between gap-4">
            <div>
                <h2 class="text-xl font-bold text-white">Business Lead Ingestion & Qualification Hub</h2>
                <p class="text-sm text-slate-400 mt-1">Real-time sync active: Submissions on /apply immediately stream here.</p>
            </div>
            <div class="flex flex-wrap items-center gap-3 w-full md:w-auto">
                <button id="loadSampleBtn" onclick="loadSampleLeads()" class="px-4 py-2.5 rounded-xl border border-slate-700 bg-slate-800 hover:bg-slate-700 text-sm font-semibold text-slate-200 transition shadow-sm flex items-center justify-center gap-2">
                    <svg class="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                    Reload Baseline Leads
                </button>
                <button id="runBtn" onclick="runAutomation()" class="px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-600 hover:from-indigo-600 hover:to-violet-700 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 transition flex items-center justify-center gap-2">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    Run Pipeline
                </button>
                <button id="exportCsvBtn" onclick="exportCleanCsv()" class="px-4 py-2.5 rounded-xl border border-emerald-500/30 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 text-sm font-semibold transition flex items-center justify-center gap-2">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                    Export Clean CSV
                </button>
            </div>
        </div>

        <!-- Metric Summary Cards -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="bg-slate-900/60 border border-slate-800 rounded-2xl p-5">
                <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Total Leads Ingested</span>
                <div class="mt-2 flex items-baseline justify-between">
                    <span id="metricTotal" class="text-3xl font-extrabold text-white">0</span>
                    <span class="text-xs text-slate-500 font-mono">records</span>
                </div>
            </div>
            <div class="bg-slate-900/60 border border-slate-800 rounded-2xl p-5">
                <span class="text-xs font-semibold uppercase tracking-wider text-emerald-400">Successfully Qualified</span>
                <div class="mt-2 flex items-baseline justify-between">
                    <span id="metricValid" class="text-3xl font-extrabold text-emerald-400">0</span>
                    <span class="text-xs text-emerald-500 font-mono">validated</span>
                </div>
            </div>
            <div class="bg-slate-900/60 border border-slate-800 rounded-2xl p-5">
                <span class="text-xs font-semibold uppercase tracking-wider text-indigo-400">Total Pipeline Value</span>
                <div class="mt-2 flex items-baseline justify-between">
                    <span id="metricPipeline" class="text-3xl font-extrabold text-indigo-400">$0.00</span>
                    <span class="text-xs text-indigo-500 font-mono">USD</span>
                </div>
            </div>
            <div class="bg-slate-900/60 border border-slate-800 rounded-2xl p-5">
                <span class="text-xs font-semibold uppercase tracking-wider text-rose-400">Validation Failures</span>
                <div class="mt-2 flex items-baseline justify-between">
                    <span id="metricInvalid" class="text-3xl font-extrabold text-rose-400">0</span>
                    <span class="text-xs text-rose-500 font-mono">rejected</span>
                </div>
            </div>
        </div>

        <!-- Main Workspace: Form & Leads Queue -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <!-- Left: Add Lead Form -->
            <div class="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 space-y-4">
                <div class="flex items-center justify-between pb-3 border-b border-slate-800">
                    <h3 class="font-bold text-white flex items-center gap-2">
                        <svg class="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" /></svg>
                        Add Manual Lead
                    </h3>
                    <span class="text-xs text-slate-500">Live schema ingress</span>
                </div>

                <form id="leadForm" onsubmit="addLeadFromForm(event)" class="space-y-3">
                    <div>
                        <label class="block text-xs font-semibold text-slate-300 mb-1">Lead ID</label>
                        <input type="text" id="formLeadId" required placeholder="e.g. LD-100" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-300 mb-1">Contact Name</label>
                        <input type="text" id="formName" required placeholder="e.g. Mahir Faisal" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-300 mb-1">Email Address</label>
                        <input type="email" id="formEmail" required placeholder="e.g. mahir@techscale.io" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-300 mb-1">Company</label>
                        <input type="text" id="formCompany" required placeholder="e.g. TechScale Solutions" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500">
                    </div>
                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-semibold text-slate-300 mb-1">Budget ($ USD)</label>
                            <input type="number" id="formBudget" step="500" required placeholder="65000" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500">
                        </div>
                        <div>
                            <label class="block text-xs font-semibold text-slate-300 mb-1">Industry</label>
                            <select id="formIndustry" class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500">
                                <option value="FinTech">FinTech</option>
                                <option value="AI">AI & ML</option>
                                <option value="SaaS">SaaS</option>
                                <option value="Healthcare">Healthcare</option>
                                <option value="E-Commerce">E-Commerce</option>
                                <option value="General">General</option>
                            </select>
                        </div>
                    </div>
                    <button type="submit" class="w-full mt-2 py-2.5 rounded-xl border border-indigo-500/30 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 text-sm font-semibold transition flex items-center justify-center gap-2">
                        Add to Ingestion Queue
                    </button>
                </form>
            </div>

            <!-- Right: Queue & Raw JSON View -->
            <div class="lg:col-span-2 bg-slate-900/70 border border-slate-800 rounded-2xl p-6 space-y-4">
                <div class="flex items-center justify-between pb-3 border-b border-slate-800">
                    <div>
                        <h3 class="font-bold text-white">Live Ingestion Stream</h3>
                        <p class="text-xs text-slate-400">Synchronized with public submissions on /apply (<span id="queueCount">0</span> items)</p>
                    </div>
                    <div class="flex items-center gap-3">
                        <span class="text-xs text-emerald-400 flex items-center gap-1 font-mono">
                            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
                            Auto-sync: 3s
                        </span>
                        <button onclick="clearQueue()" class="text-xs text-slate-400 hover:text-rose-400 transition">
                            Clear Queue
                        </button>
                    </div>
                </div>
                <div class="relative">
                    <textarea id="jsonQueue" rows="11" class="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 font-mono text-xs text-slate-300 focus:outline-none focus:border-indigo-500 leading-relaxed"></textarea>
                </div>
            </div>
        </div>

        <!-- Live Qualified Leads & VIP Badges Table -->
        <div class="bg-slate-900/70 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
            <div class="p-6 border-b border-slate-800 flex items-center justify-between">
                <div>
                    <h3 class="font-bold text-white text-lg">Qualified Leads & Scoring Results</h3>
                    <p class="text-xs text-slate-400">Real-time classification with automated VIP routing and tailored AI email drafts</p>
                </div>
            </div>

            <div class="overflow-x-auto">
                <table class="w-full text-left text-sm text-slate-300">
                    <thead class="bg-slate-950/60 text-xs font-semibold uppercase text-slate-400 border-b border-slate-800">
                        <tr>
                            <th class="px-6 py-3.5">Lead / Contact</th>
                            <th class="px-6 py-3.5">Company & Industry</th>
                            <th class="px-6 py-3.5">Budget</th>
                            <th class="px-6 py-3.5">Priority Tier</th>
                            <th class="px-6 py-3.5">Score</th>
                            <th class="px-6 py-3.5">AI Follow-up & Actions</th>
                        </tr>
                    </thead>
                    <tbody id="resultsTableBody" class="divide-y divide-slate-800/60">
                        <tr>
                            <td colspan="6" class="px-6 py-10 text-center text-slate-500 italic">
                                Initializing live pipeline stream...
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Rejection & Error Audit Log (Appears if failures exist) -->
        <div id="errorLogSection" class="hidden bg-rose-950/20 border border-rose-900/40 rounded-2xl p-6 space-y-3">
            <div class="flex items-center gap-2 text-rose-400 font-bold">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                <span>Validation Failure & Rejection Audit Log</span>
            </div>
            <p class="text-xs text-rose-300/80">The pipeline rejected these records due to schema violations without breaking valid lead processing:</p>
            <div id="errorLogList" class="space-y-2 mt-2 font-mono text-xs"></div>
        </div>
    </main>

    <!-- AI Follow-up Email Modal -->
    <div id="emailModal" class="hidden fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
        <div class="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 space-y-4 shadow-2xl relative">
            <div class="flex items-center justify-between pb-3 border-b border-slate-800">
                <div class="flex items-center gap-2">
                    <span class="text-xl">✉️</span>
                    <h3 class="font-bold text-white text-base">Generated AI Follow-Up Email Draft</h3>
                </div>
                <button onclick="closeEmailModal()" class="text-slate-400 hover:text-white transition text-lg">&times;</button>
            </div>
            <div>
                <span id="modalLeadInfo" class="text-xs font-semibold text-indigo-400"></span>
                <div class="mt-2 relative">
                    <pre id="modalEmailContent" class="bg-slate-950 border border-slate-800 rounded-xl p-4 text-xs font-mono text-slate-200 whitespace-pre-wrap leading-relaxed max-h-96 overflow-y-auto"></pre>
                </div>
            </div>
            <div class="flex items-center justify-end gap-3 pt-2">
                <button onclick="copyModalEmail()" id="copyEmailBtn" class="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-xs font-bold text-white transition flex items-center gap-1.5 shadow-lg shadow-indigo-600/20">
                    <span>📋 Copy Email</span>
                </button>
                <button onclick="closeEmailModal()" class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300 transition">
                    Close
                </button>
            </div>
        </div>
    </div>

    <!-- Client-Side Dashboard Logic -->
    <script>
        let currentQueue = [];
        let currentQualifiedLeads = [];
        let isUserEditingQueue = false;

        document.getElementById('jsonQueue').addEventListener('focus', () => { isUserEditingQueue = true; });
        document.getElementById('jsonQueue').addEventListener('blur', () => { isUserEditingQueue = false; });

        function updateQueueDisplay() {
            if (!isUserEditingQueue) {
                document.getElementById('jsonQueue').value = JSON.stringify(currentQueue, null, 2);
            }
            document.getElementById('queueCount').innerText = currentQueue.length;
        }

        async function fetchLiveStatus() {
            try {
                const res = await fetch('/api/live-status');
                if (!res.ok) return;
                const data = await res.json();
                currentQueue = data.raw_queue;
                currentQualifiedLeads = data.leads;
                updateQueueDisplay();
                renderResults(data);
            } catch (err) {
                console.error("Live fetch error:", err);
            }
        }

        async function loadSampleLeads() {
            try {
                const res = await fetch('/api/sample-leads');
                currentQueue = await res.json();
                updateQueueDisplay();
                runAutomation();
            } catch (err) {
                alert('Error loading sample leads: ' + err.message);
            }
        }

        function clearQueue() {
            currentQueue = [];
            updateQueueDisplay();
        }

        function addLeadFromForm(e) {
            e.preventDefault();
            const lead = {
                lead_id: document.getElementById('formLeadId').value.trim(),
                name: document.getElementById('formName').value.trim(),
                email: document.getElementById('formEmail').value.trim(),
                company: document.getElementById('formCompany').value.trim(),
                budget: parseFloat(document.getElementById('formBudget').value),
                industry: document.getElementById('formIndustry').value,
                source: "Dashboard Manual Form"
            };
            currentQueue.unshift(lead);
            updateQueueDisplay();
            document.getElementById('leadForm').reset();
            runAutomation();
        }

        async function runAutomation() {
            try {
                const text = document.getElementById('jsonQueue').value.trim();
                if (text) {
                    currentQueue = JSON.parse(text);
                }
            } catch (err) {
                alert('Invalid JSON in queue editor: ' + err.message);
                return;
            }

            const res = await fetch('/api/process-leads', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ leads: currentQueue })
            });

            if (res.ok) {
                const data = await res.json();
                currentQualifiedLeads = data.leads;
                renderResults(data);
            }
        }

        async function exportCleanCsv() {
            if (!currentQueue || currentQueue.length === 0) {
                alert('Queue is empty. No leads to export.');
                return;
            }

            try {
                const res = await fetch('/api/export-csv', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ leads: currentQueue })
                });

                if (!res.ok) throw new Error('CSV generation failed');

                const blob = await res.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = `qualified_leads_${new Date().toISOString().slice(0, 10)}.csv`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                a.remove();
            } catch (err) {
                alert('Export failed: ' + err.message);
            }
        }

        function renderResults(data) {
            const { leads, summary } = data;

            document.getElementById('metricTotal').innerText = summary.total_received;
            document.getElementById('metricValid').innerText = summary.total_valid;
            document.getElementById('metricPipeline').innerText = '$' + summary.total_pipeline_value.toLocaleString('en-US', { minimumFractionDigits: 2 });
            document.getElementById('metricInvalid').innerText = summary.total_invalid;

            // VIP Alerts Banner
            const vipBanner = document.getElementById('vipAlertBanner');
            const vipBadgesContainer = document.getElementById('vipAlertBadges');
            if (summary.vip_alerts && summary.vip_alerts.length > 0) {
                vipBanner.classList.remove('hidden');
                vipBadgesContainer.innerHTML = summary.vip_alerts.map(a => `
                    <div class="px-3 py-1.5 rounded-xl bg-purple-900/60 border border-purple-500/50 text-xs flex items-center gap-2 shadow-lg">
                        <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                        <span class="font-bold text-white">${a.company}</span>
                        <span class="font-mono text-purple-200">($${a.budget.toLocaleString()})</span>
                        <span class="text-[10px] bg-purple-500/30 px-1.5 py-0.5 rounded text-purple-200">Telegram Dispatched</span>
                    </div>
                `).join('');
            } else {
                vipBanner.classList.add('hidden');
            }

            // Table
            const tbody = document.getElementById('resultsTableBody');
            if (!leads || leads.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" class="px-6 py-6 text-center text-slate-500">No qualified leads generated.</td></tr>`;
            } else {
                tbody.innerHTML = leads.map((lead, idx) => {
                    let badge = '';
                    if (lead.tier === 'ENTERPRISE') {
                        badge = `<span class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40">
                            ⭐ VIP Enterprise
                        </span>`;
                    } else if (lead.tier === 'GROWTH') {
                        badge = `<span class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                            🚀 Growth Tier
                        </span>`;
                    } else if (lead.tier === 'STANDARD') {
                        badge = `<span class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-blue-500/20 text-blue-300 border border-blue-500/40">
                            💼 Standard
                        </span>`;
                    } else {
                        badge = `<span class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700">
                            ⚪ Unqualified
                        </span>`;
                    }

                    return `
                        <tr class="hover:bg-slate-800/30 transition">
                            <td class="px-6 py-4">
                                <div class="font-semibold text-white">${lead.name}</div>
                                <div class="text-xs text-slate-400 font-mono">${lead.email}</div>
                                <div class="text-[10px] text-slate-500 font-mono">${lead.lead_id}</div>
                            </td>
                            <td class="px-6 py-4">
                                <div class="text-white">${lead.company}</div>
                                <div class="text-xs text-indigo-400">${lead.industry}</div>
                            </td>
                            <td class="px-6 py-4 font-mono font-semibold text-emerald-400">
                                $${lead.budget.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                            </td>
                            <td class="px-6 py-4">
                                ${badge}
                            </td>
                            <td class="px-6 py-4">
                                <span class="px-2.5 py-1 rounded-lg bg-slate-800 border border-slate-700 text-xs font-mono font-bold text-indigo-300">
                                    ${lead.score}/100
                                </span>
                            </td>
                            <td class="px-6 py-4">
                                <button onclick="viewEmailDraft(${idx})" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/30 text-xs font-semibold text-indigo-300 transition">
                                    <span>✉️ AI Draft</span>
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('');
            }

            // Error log
            const errSection = document.getElementById('errorLogSection');
            const errList = document.getElementById('errorLogList');
            if (summary.validation_errors && summary.validation_errors.length > 0) {
                errSection.classList.remove('hidden');
                errList.innerHTML = summary.validation_errors.map(err => `
                    <div class="bg-rose-950/40 border border-rose-900/50 rounded-lg p-3 text-rose-300">
                        <span class="font-semibold text-rose-200">Record #${err.batch_index} [${err.error_type}]:</span>
                        <div class="mt-1 text-slate-300 whitespace-pre-wrap">${err.error_details}</div>
                    </div>
                `).join('');
            } else {
                errSection.classList.add('hidden');
            }
        }

        function viewEmailDraft(idx) {
            const lead = currentQualifiedLeads[idx];
            if (!lead) return;

            document.getElementById('modalLeadInfo').innerText = `${lead.name} • ${lead.company} (${lead.tier})`;
            document.getElementById('modalEmailContent').innerText = lead.email_draft || 'No email draft available.';
            document.getElementById('emailModal').classList.remove('hidden');
        }

        function closeEmailModal() {
            document.getElementById('emailModal').classList.add('hidden');
        }

        function copyModalEmail() {
            const content = document.getElementById('modalEmailContent').innerText;
            navigator.clipboard.writeText(content).then(() => {
                const btn = document.getElementById('copyEmailBtn');
                btn.innerHTML = '<span>✅ Copied!</span>';
                setTimeout(() => {
                    btn.innerHTML = '<span>📋 Copy Email</span>';
                }, 2000);
            });
        }

        // Initialize and start live polling every 3 seconds
        window.addEventListener('DOMContentLoaded', () => {
            fetchLiveStatus();
            setInterval(fetchLiveStatus, 3000);
        });
    </script>
</body>
</html>
"""


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)

