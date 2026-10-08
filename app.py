"""
Module: app.py
Description: FastAPI web dashboard for SBMC LeadAutomationService.
Provides interactive UI, sample data loader, live scoring, VIP badges, and metric cards.
"""

from typing import Any, Dict, List
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

from automation_service import LeadAutomationService

app = FastAPI(
    title="SBMC Lead Automation Dashboard",
    description="Business Automation & Lead Qualification Service with Real-time Validation",
    version="1.0.0",
)

service = LeadAutomationService()

SAMPLE_LEADS_DATA: List[Dict[str, Any]] = [
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
    {
        "lead_id": "LD-MALFORMED",
        "name": "Zahidul Alam",
        "email": "invalid-email-address",
        "company": "Faulty Data Entry Ltd",
        "budget": -2500.0,
        "industry": "Unknown",
        "source": "Corrupted Webhook",
    },
]


class ProcessLeadsRequest(BaseModel):
    leads: List[Dict[str, Any]]


@app.get("/api/sample-leads")
def get_sample_leads() -> List[Dict[str, Any]]:
    """Returns curated realistic sample leads for quick demonstration."""
    return SAMPLE_LEADS_DATA


@app.post("/api/process-leads")
def process_leads(payload: ProcessLeadsRequest) -> Dict[str, Any]:
    """Ingests raw leads batch, runs validation and tier scoring, and returns pipeline metrics."""
    if not payload.leads:
        raise HTTPException(status_code=400, detail="Leads list cannot be empty.")

    qualified_leads, summary = service.process_batch(payload.leads)
    return {
        "leads": [lead.model_dump() for lead in qualified_leads],
        "summary": summary.model_dump(),
    }


@app.get("/", response_class=HTMLResponse)
def dashboard_ui() -> str:
    """Renders the comprehensive, modern dashboard HTML user interface."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SBMC Lead Automation Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Plus Jakarta Sans', sans-serif; }
    </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen">
    <!-- Top Navigation -->
    <header class="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
                    <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                </div>
                <div>
                    <h1 class="font-bold text-lg text-white leading-tight">SBMC Automation Engine</h1>
                    <p class="text-xs text-slate-400">Module M4 • Intelligent Lead Qualification & Scoring</p>
                </div>
            </div>
            <div class="flex items-center gap-4">
                <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                    API Active (FastAPI)
                </span>
                <a href="/docs" target="_blank" class="text-xs text-slate-400 hover:text-white transition flex items-center gap-1">
                    API Docs &rarr;
                </a>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        <!-- Control Actions Banner -->
        <div class="bg-gradient-to-r from-slate-900 via-indigo-950/40 to-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col md:flex-row items-center justify-between gap-4">
            <div>
                <h2 class="text-xl font-bold text-white">Business Lead Ingestion & Scoring Hub</h2>
                <p class="text-sm text-slate-400 mt-1">Submit single leads or trigger batch automation with full Pydantic validation & resilience.</p>
            </div>
            <div class="flex items-center gap-3 w-full md:w-auto">
                <button id="loadSampleBtn" onclick="loadSampleLeads()" class="flex-1 md:flex-initial px-4 py-2.5 rounded-xl border border-slate-700 bg-slate-800 hover:bg-slate-700 text-sm font-semibold text-slate-200 transition shadow-sm flex items-center justify-center gap-2">
                    <svg class="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                    </svg>
                    Load Sample Leads
                </button>
                <button id="runBtn" onclick="runAutomation()" class="flex-1 md:flex-initial px-6 py-2.5 rounded-xl bg-gradient-to-r from-indigo-500 to-violet-600 hover:from-indigo-600 hover:to-violet-700 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 transition flex items-center justify-center gap-2">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Run Automation
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
                        <svg class="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
                        </svg>
                        Add Custom Lead
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
                        <h3 class="font-bold text-white">Ingestion Queue Preview</h3>
                        <p class="text-xs text-slate-400">Leads waiting for validation and scoring (<span id="queueCount">0</span> items)</p>
                    </div>
                    <button onclick="clearQueue()" class="text-xs text-slate-400 hover:text-rose-400 transition">
                        Clear Queue
                    </button>
                </div>
                <div class="relative">
                    <textarea id="jsonQueue" rows="11" class="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 font-mono text-xs text-slate-300 focus:outline-none focus:border-indigo-500 leading-relaxed" placeholder="Click 'Load Sample Leads' or add leads using the form above..."></textarea>
                </div>
            </div>
        </div>

        <!-- Live Qualified Leads & VIP Badges Table -->
        <div class="bg-slate-900/70 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
            <div class="p-6 border-b border-slate-800 flex items-center justify-between">
                <div>
                    <h3 class="font-bold text-white text-lg">Qualified Leads & Scoring Results</h3>
                    <p class="text-xs text-slate-400">Classified into tiers with dynamic scoring notes and status badges</p>
                </div>
                <div id="tierPills" class="flex items-center gap-2"></div>
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
                            <th class="px-6 py-3.5">Qualification Notes</th>
                        </tr>
                    </thead>
                    <tbody id="resultsTableBody" class="divide-y divide-slate-800/60">
                        <tr>
                            <td colspan="6" class="px-6 py-10 text-center text-slate-500 italic">
                                No automation run yet. Click "Load Sample Leads" and then "Run Automation".
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Rejection & Error Audit Log (Appears if failures exist) -->
        <div id="errorLogSection" class="hidden bg-rose-950/20 border border-rose-900/40 rounded-2xl p-6 space-y-3">
            <div class="flex items-center gap-2 text-rose-400 font-bold">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span>Validation Failure & Rejection Audit Log</span>
            </div>
            <p class="text-xs text-rose-300/80">The pipeline rejected these records due to schema violations without breaking valid lead processing:</p>
            <div id="errorLogList" class="space-y-2 mt-2 font-mono text-xs"></div>
        </div>
    </main>

    <!-- Client-Side Dashboard Logic -->
    <script>
        let currentQueue = [];

        function updateQueueDisplay() {
            document.getElementById('jsonQueue').value = JSON.stringify(currentQueue, null, 2);
            document.getElementById('queueCount').innerText = currentQueue.length;
        }

        async function loadSampleLeads() {
            try {
                const res = await fetch('/api/sample-leads');
                currentQueue = await res.json();
                updateQueueDisplay();
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
                source: "Dashboard Web Form"
            };
            currentQueue.push(lead);
            updateQueueDisplay();
            document.getElementById('leadForm').reset();
        }

        async function runAutomation() {
            // Sync current editor state
            try {
                const text = document.getElementById('jsonQueue').value.trim();
                if (text) {
                    currentQueue = JSON.parse(text);
                }
            } catch (err) {
                alert('Invalid JSON in queue editor: ' + err.message);
                return;
            }

            if (!currentQueue || currentQueue.length === 0) {
                alert('Please load sample leads or add leads to the queue first.');
                return;
            }

            const btn = document.getElementById('runBtn');
            btn.disabled = true;
            btn.innerText = 'Running Pipeline...';

            try {
                const res = await fetch('/api/process-leads', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ leads: currentQueue })
                });

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Failed to process leads');
                }

                const data = await res.json();
                renderResults(data);
            } catch (err) {
                alert('Automation run failed: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = `
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Run Automation
                `;
            }
        }

        function renderResults(data) {
            const { leads, summary } = data;

            // Update top metrics
            document.getElementById('metricTotal').innerText = summary.total_received;
            document.getElementById('metricValid').innerText = summary.total_valid;
            document.getElementById('metricPipeline').innerText = '$' + summary.total_pipeline_value.toLocaleString('en-US', { minimumFractionDigits: 2 });
            document.getElementById('metricInvalid').innerText = summary.total_invalid;

            // Render table
            const tbody = document.getElementById('resultsTableBody');
            if (!leads || leads.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" class="px-6 py-6 text-center text-slate-500">No qualified leads generated.</td></tr>`;
            } else {
                tbody.innerHTML = leads.map(lead => {
                    let badge = '';
                    if (lead.tier === 'ENTERPRISE') {
                        badge = `<span class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-purple-500/15 text-purple-300 border border-purple-500/30">
                            ⭐ VIP Enterprise
                        </span>`;
                    } else if (lead.tier === 'GROWTH') {
                        badge = `<span class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                            🚀 Growth Tier
                        </span>`;
                    } else if (lead.tier === 'STANDARD') {
                        badge = `<span class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-blue-500/15 text-blue-300 border border-blue-500/30">
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
                            <td class="px-6 py-4 text-xs text-slate-300">
                                ${lead.qualification_notes}
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

        // Preload sample leads on first load
        window.addEventListener('DOMContentLoaded', loadSampleLeads);
    </script>
</body>
</html>
"""


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
