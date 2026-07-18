// State management
let state = {
    incidents: {},
    postmortems: [],
    evaluations: [],
    auditLogs: [],
    activeIncidentId: null
};

let telemetryChart = null;
let ws = null;

// Initialize Lucide Icons on document load
document.addEventListener("DOMContentLoaded", () => {
    lucide.createIcons();
    initNavigation();
    initChart();
    connectWebSocket();
    
    // Wire up approve button
    document.getElementById("approve-btn").addEventListener("click", () => {
        if (state.activeIncidentId) {
            approveRemediation(state.activeIncidentId);
        }
    });
});

// Navigation logic between tabs
function initNavigation() {
    const navButtons = document.querySelectorAll(".nav-btn");
    const views = document.querySelectorAll(".view-panel");

    navButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            navButtons.forEach(b => b.classList.remove("active"));
            views.forEach(v => v.classList.remove("active"));

            btn.classList.add("active");
            const target = btn.getAttribute("data-target");
            document.getElementById(target).classList.add("active");
        });
    });
}

// Chart.js initialization
function initChart() {
    const ctx = document.getElementById("telemetryChart").getContext("2d");
    telemetryChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'API Gateway Latency (ms)',
                    data: [],
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99, 102, 241, 0.05)',
                    fill: true,
                    tension: 0.3,
                    yAxisID: 'y'
                },
                {
                    label: 'DB Active Connections',
                    data: [],
                    borderColor: '#fbbf24',
                    backgroundColor: 'rgba(251, 191, 36, 0.02)',
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: '#94a3b8', font: { family: 'Outfit' } }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.04)' },
                    ticks: { color: '#64748b', font: { family: 'Outfit' } }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    grid: { color: 'rgba(255, 255, 255, 0.04)' },
                    ticks: { color: '#94a3b8', font: { family: 'Outfit' } },
                    title: { display: true, text: 'Latency (ms)', color: '#94a3b8' }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    grid: { drawOnChartArea: false },
                    ticks: { color: '#fbbf24', font: { family: 'Outfit' } },
                    title: { display: true, text: 'Connections', color: '#fbbf24' }
                }
            }
        }
    });
}

// WebSocket Connection handling
function connectWebSocket() {
    const wsUrl = `ws://${window.location.hostname || '127.0.0.1'}:8080/ws`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log("AIRE backend websocket link established.");
    };

    ws.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        const data = payload.data;
        
        switch (payload.event) {
            case "init_state":
                // Parse incidents list to mapping
                state.incidents = {};
                data.incidents.forEach(inc => {
                    state.incidents[inc.id] = inc;
                });
                state.postmortems = data.postmortems;
                state.evaluations = data.evaluations;
                state.auditLogs = data.audit_logs;
                
                // If any incident exists, set first active
                const keys = Object.keys(state.incidents);
                if (keys.length > 0 && !state.activeIncidentId) {
                    state.activeIncidentId = keys[keys.length - 1]; // most recent
                }
                
                renderAll();
                break;
                
            case "incident_detected":
                state.incidents[data.id] = data;
                state.activeIncidentId = data.id;
                renderAll();
                break;
                
            case "incident_updated":
                state.incidents[data.id] = data;
                if (state.activeIncidentId === data.id) {
                    renderActiveIncidentDetails();
                }
                renderIncidentsList();
                break;
                
            case "postmortem_created":
                state.postmortems.unshift(data);
                renderPostmortems();
                break;
                
            case "evaluation_updated":
                state.evaluations.unshift(data);
                renderEvaluations();
                break;
                
            case "audit_logged":
                state.auditLogs.unshift(data);
                renderAuditLogs();
                break;
        }
    };

    ws.onclose = () => {
        console.warn("WebSocket closed. Attempting reconnect in 3 seconds...");
        setTimeout(connectWebSocket, 3000);
    };
}

// API Calls
async function triggerOutage(type) {
    try {
        const res = await fetch(`http://127.0.0.1:8080/api/incidents/trigger?incident_type=${type}`, { method: 'POST' });
        const result = await res.json();
        console.log("Trigger response:", result);
    } catch (e) {
        console.error("Failed to trigger outage:", e);
    }
}

async function resetEnvironment() {
    try {
        const res = await fetch(`http://127.0.0.1:8080/api/environment/reset`, { method: 'POST' });
        state = { incidents: {}, postmortems: [], evaluations: [], auditLogs: [], activeIncidentId: null };
        renderAll();
        // Clear chart
        telemetryChart.data.labels = [];
        telemetryChart.data.datasets[0].data = [];
        telemetryChart.data.datasets[1].data = [];
        telemetryChart.update();
    } catch (e) {
        console.error("Failed to reset environment:", e);
    }
}

async function approveRemediation(incidentId) {
    try {
        const res = await fetch(`http://127.0.0.1:8080/api/incidents/${incidentId}/approve?actor=LeadSRE`, { method: 'POST' });
        const result = await res.json();
        console.log("Approval response:", result);
    } catch (e) {
        console.error("Failed to approve remediation:", e);
    }
}

// Rendering components
function renderAll() {
    renderSystemIndicator();
    renderIncidentsList();
    renderActiveIncidentDetails();
    renderPostmortems();
    renderEvaluations();
    renderAuditLogs();
}

function renderSystemIndicator() {
    const pulse = document.getElementById("system-status-pulse");
    const title = document.getElementById("system-status-title");
    
    // Check if there are any active unresolved incidents
    const activeIncs = Object.values(state.incidents).filter(inc => inc.status !== "RESOLVED");
    
    if (activeIncs.length > 0) {
        pulse.className = "pulse-indicator incident";
        title.innerText = `${activeIncs.length} Outage(s) Active`;
    } else {
        pulse.className = "pulse-indicator healthy";
        title.innerText = "System Healthy";
    }
}

function renderIncidentsList() {
    const container = document.getElementById("incidents-container");
    const incs = Object.values(state.incidents);
    
    if (incs.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i data-lucide="check-circle-2"></i>
                <p>No active incidents detected. Production environments healthy.</p>
            </div>`;
        lucide.createIcons();
        return;
    }
    
    // Sort reverse chronological
    incs.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    
    container.innerHTML = incs.map(inc => {
        const isActive = state.activeIncidentId === inc.id ? "active" : "";
        const createdDate = new Date(inc.created_at).toLocaleTimeString();
        return `
            <div class="incident-card ${isActive} ${inc.severity}" onclick="selectIncident('${inc.id}')">
                <div class="inc-info">
                    <span class="inc-title">${inc.title}</span>
                    <span class="inc-meta">ID: ${inc.id} | Service: ${inc.service} | Triggered: ${createdDate}</span>
                </div>
                <span class="badge badge-status ${inc.status}">${inc.status}</span>
            </div>
        `;
    }).join('');
}

function selectIncident(id) {
    state.activeIncidentId = id;
    renderIncidentsList();
    renderActiveIncidentDetails();
}

function renderActiveIncidentDetails() {
    const incident = state.incidents[state.activeIncidentId];
    const timelineContainer = document.getElementById("timeline-container");
    const approvalGate = document.getElementById("approval-gate-container");
    const logsBody = document.getElementById("logs-body");
    
    if (!incident) {
        timelineContainer.innerHTML = `
            <div class="timeline-empty-state">
                <p>Select or trigger an incident to view the AI investigator reasoning logs.</p>
            </div>`;
        approvalGate.style.display = "none";
        return;
    }
    
    // 1. Render timeline agent tasks
    if (incident.tasks.length === 0) {
        timelineContainer.innerHTML = `<div class="timeline-empty-state"><p>Agent swarm analyzing initial alert state...</p></div>`;
    } else {
        timelineContainer.innerHTML = incident.tasks.map(task => {
            const statusMarker = task.status; // SUCCESS, RUNNING, PENDING
            const findingsContent = task.findings 
                ? `<div class="node-findings">${task.findings}</div>` 
                : `<div class="node-findings font-italic text-muted">Agent task executing: querying metrics/logs systems...</div>`;
            return `
                <div class="timeline-node">
                    <div class="timeline-marker ${statusMarker}"></div>
                    <div class="timeline-card">
                        <div class="node-header">
                            <span class="node-agent">${task.agent_name}</span>
                            <span class="node-status badge badge-status">${task.status}</span>
                        </div>
                        <div class="node-desc">${task.description}</div>
                        ${findingsContent}
                    </div>
                </div>
            `;
        }).join('');
    }
    
    // 2. Human approval Gate Visibility
    if (incident.status === "IDENTIFIED" && !incident.remediation_executed) {
        approvalGate.style.display = "block";
        document.getElementById("approval-description").innerText = `Swarm proposes: '${incident.proposed_remediation}'. Click to authorize.`;
    } else {
        approvalGate.style.display = "none";
    }
    
    // 3. Update simulated logs console
    fetchLokiLogsMock(incident.service, incident.status);
    
    // 4. Update metrics charts
    fetchPrometheusMetricsMock(incident.service, incident.status);
}

// Fetch and append mock logs based on active state
async function fetchLokiLogsMock(service, status) {
    const logsBody = document.getElementById("logs-body");
    try {
        const query = status === "RESOLVED" ? "info" : "error";
        const res = await fetch(`http://127.0.0.1:8080/api/security/audit`); // Just dummy hit or query local Loki api
        
        // Generate realistic local UI logs
        let mockLines = [];
        const now = new Date();
        
        if (status !== "RESOLVED") {
            if (service === "payment-service") {
                mockLines = [
                    { time: now.toLocaleTimeString(), svc: "kubernetes", lvl: "WARN", msg: "Pod payment-service-5c6e8f-xyz34 failed liveness probe, restarting." },
                    { time: now.toLocaleTimeString(), svc: "payment-service", lvl: "ERROR", msg: "FATAL EXCEPTION: OutOfMemoryError: Java heap space" },
                    { time: now.toLocaleTimeString(), svc: "payment-service", lvl: "ERROR", msg: "at java.util.concurrent.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:1149)" }
                ];
            } else if (service === "payment-db") {
                mockLines = [
                    { time: now.toLocaleTimeString(), svc: "payment-db", lvl: "FATAL", msg: "FATAL: remaining connection slots are reserved for non-replication superuser connections" },
                    { time: now.toLocaleTimeString(), svc: "payment-service", lvl: "ERROR", msg: "HikariPool-1 - Connection is not available, request timed out after 30000ms." }
                ];
            } else if (service === "auth-service" || service === "api-gateway") {
                mockLines = [
                    { time: now.toLocaleTimeString(), svc: "auth-service", lvl: "WARN", msg: "Slow response from crypto verify. CPU throttling active." },
                    { time: now.toLocaleTimeString(), svc: "api-gateway", lvl: "WARN", msg: "Upstream response slow from service 'auth-service' duration_ms=1850" }
                ];
            } else if (service === "notification-service") {
                mockLines = [
                    { time: now.toLocaleTimeString(), svc: "notification-service", lvl: "ERROR", msg: "Uncaught TypeError: Cannot read property 'template_id' of undefined at Mailer.send" }
                ];
            }
        } else {
            mockLines = [
                { time: now.toLocaleTimeString(), svc: "api-gateway", lvl: "INFO", msg: "GET /api/v1/payments - 200 OK - 15.42ms" },
                { time: now.toLocaleTimeString(), svc: "payment-service", lvl: "INFO", msg: "Transaction processed successfully tx_id=98715" },
                { time: now.toLocaleTimeString(), svc: "kubernetes", lvl: "INFO", msg: "Service mesh routing restored. Health checks green." }
            ];
        }
        
        logsBody.innerHTML = mockLines.map(log => `
            <div class="log-line">
                <span class="log-time">${log.time}</span>
                <span class="log-svc">[${log.svc}]</span>
                <span class="log-lvl ${log.lvl}">${log.lvl}</span>
                <span class="log-msg">${log.msg}</span>
            </div>
        `).join('');
        
        logsBody.scrollTop = logsBody.scrollHeight;
    } catch (e) {
        console.error(e);
    }
}

// Generate metric chart data
async function fetchPrometheusMetricsMock(service, status) {
    if (!telemetryChart) return;
    
    // Make 10 data labels
    const labels = [];
    const latencyData = [];
    const connectionData = [];
    
    const now = new Date();
    for (let i = 9; i >= 0; i--) {
        const timeStr = new Date(now - i * 10 * 1000).toLocaleTimeString();
        labels.push(timeStr);
        
        if (status !== "RESOLVED") {
            // Outage values
            if (service === "payment-db") {
                latencyData.push(Math.random() * 500 + 800); // 800 - 1300 ms
                connectionData.push(100 - i); // Escalating connections
            } else if (service === "auth-service" || service === "api-gateway") {
                latencyData.push(Math.random() * 1000 + 1500); // High latency
                connectionData.push(Math.floor(Math.random() * 10 + 20));
            } else {
                latencyData.push(Math.random() * 400 + 600);
                connectionData.push(Math.floor(Math.random() * 15 + 15));
            }
        } else {
            // Restored healthy values
            latencyData.push(Math.random() * 10 + 15); // 15ms latency
            connectionData.push(Math.floor(Math.random() * 5 + 18)); // 18-23 connections
        }
    }
    
    telemetryChart.data.labels = labels;
    telemetryChart.data.datasets[0].data = latencyData;
    telemetryChart.data.datasets[1].data = connectionData;
    telemetryChart.update();
}

function renderPostmortems() {
    const container = document.getElementById("postmortems-container");
    if (state.postmortems.length === 0) {
        container.innerHTML = `<div class="empty-state"><p>No postmortems recorded yet. Resolving incidents automatically generates reports.</p></div>`;
        return;
    }
    
    container.innerHTML = state.postmortems.map(pm => `
        <div class="postmortem-card">
            <div class="pm-header">
                <span class="pm-title">${pm.title}</span>
                <span class="badge ${pm.severity}">${pm.severity}</span>
            </div>
            <div class="pm-grid">
                <div class="pm-section">
                    <h5>Executive Summary</h5>
                    <p>${pm.executive_summary}</p>
                </div>
                <div class="pm-section">
                    <h5>Trigger alert</h5>
                    <p>${pm.trigger}</p>
                </div>
                <div class="pm-section">
                    <h5>Root Cause identified</h5>
                    <p>${pm.root_cause}</p>
                </div>
                <div class="pm-section">
                    <h5>Remediation details</h5>
                    <p>${pm.remediation_details}</p>
                </div>
                <div class="pm-section">
                    <h5>Action items</h5>
                    <ul>
                        ${pm.action_items.map(item => `<li>${item}</li>`).join('')}
                    </ul>
                </div>
                <div class="pm-section">
                    <h5>Preventative measures</h5>
                    <ul>
                        ${pm.preventative_measures.map(item => `<li>${item}</li>`).join('')}
                    </ul>
                </div>
            </div>
        </div>
    `).join('');
}

function renderEvaluations() {
    const tableBody = document.getElementById("evaluations-table-body");
    
    // Update metric cards based on available evaluations
    if (state.evaluations.length > 0) {
        const avgGroundedness = (state.evaluations.reduce((acc, ev) => acc + ev.faithfulness, 0) / state.evaluations.length) * 100;
        const avgMttr = state.evaluations.reduce((acc, ev) => acc + ev.latency_seconds, 0) / state.evaluations.length;
        const totalCost = state.evaluations.reduce((acc, ev) => acc + ev.token_cost_usd, 0);
        
        document.getElementById("eval-groundedness").innerText = `${avgGroundedness.toFixed(1)}%`;
        document.getElementById("eval-mttr").innerText = `${avgMttr.toFixed(1)}s`;
        document.getElementById("eval-cost").innerText = `$${totalCost.toFixed(3)}`;
        
        tableBody.innerHTML = state.evaluations.map(ev => `
            <tr>
                <td><strong>${ev.run_id}</strong></td>
                <td>${ev.incident_type}</td>
                <td>${(ev.precision * 100).toFixed(0)}%</td>
                <td>${(ev.recall * 100).toFixed(0)}%</td>
                <td>${ev.latency_seconds.toFixed(1)}s</td>
                <td>$${ev.token_cost_usd.toFixed(4)}</td>
                <td>${ev.human_rating}/5 ⭐</td>
            </tr>
        `).join('');
    } else {
        tableBody.innerHTML = `<tr><td colspan="7" class="text-center">No benchmark records evaluated yet.</td></tr>`;
    }
}

function renderAuditLogs() {
    const container = document.getElementById("audit-container");
    if (state.auditLogs.length === 0) {
        container.innerHTML = `<div class="empty-state"><p>No security boundary audits generated yet.</p></div>`;
        return;
    }
    
    container.innerHTML = state.auditLogs.map(log => {
        const timeStr = new Date(log.timestamp).toLocaleTimeString();
        return `
            <div class="audit-card">
                <span class="audit-time">${timeStr}</span>
                <span class="audit-actor">${log.actor}</span>
                <span class="audit-action">${log.action}</span>
                <span class="audit-status ${log.status}">${log.status}</span>
                <span class="audit-details">${log.details}</span>
            </div>
        `;
    }).join('');
}
