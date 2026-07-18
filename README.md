# AIRE: Multi-Agent AI Orchestration & Autonomous Agentic Workflows Platform

AIRE is a production-grade Agentic AI Orchestration Platform. It implements a collaborative swarm of specialized reasoning agents (Log Investigator, Metrics Analyzer, Kubernetes Workload Auditor, and Root Cause Reasoner) that dynamically plan, communicate, call tools, and solve complex multi-step problems inside an isolated workspace.

Rather than simple sequential pipelines, AIRE serves as a flagship demonstration of building **reliable, production-ready Agentic Systems** that execute multi-step planning, function calling, episodic memory retrieval, and self-evaluation.

---

## 🧠 Core Agentic AI Architectures

Review the deep technical specifications detailing how the agentic systems are constructed:

* **[PROMPT_ENGINEERING.md](file:///C:/Users/KALYAN/.gemini/antigravity/scratch/aire/docs/ai/PROMPT_ENGINEERING.md)**: Details structured JSON configurations, prompt boundary controls, and hybrid RAG episodic memory retrieval.
* **[ARCHITECTURE.md](file:///C:/Users/KALYAN/.gemini/antigravity/scratch/aire/docs/architecture/ARCHITECTURE.md)**: Documents the system thread pools, SQLAlchemy database checkpointing, and non-blocking executors.

---

## 🏛️ Agentic Swarm Architecture Diagram

```mermaid
graph TD
    subgraph Client Layer
        WebUI[Glassmorphic Web Dashboard]
        WS[WebSocket Live State Stream]
    end

    subgraph API Gateway & Context Control
        API[FastAPI Gateway]
        DB[(SQLite state Checkpoints)]
    end

    subgraph Agentic Planner & Memory
        Orchestrator[SRE Orchestrator]
        RAG[RAG Long-Term Episodic Memory]
    end

    subgraph Reasoning Swarm Workers
        Agent1[Log Investigator Agent]
        Agent2[Metrics Investigator Agent]
        Agent3[Kubernetes Workload Agent]
        Agent4[Root Cause Synthesis Agent]
        Agent5[Remediation Driver Agent]
        Agent6[Verification Auditor Agent]
    end

    subgraph SRE Tool Call Registry
        K8s[Kubernetes API Tool]
        Prom[Prometheus Metrics Tool]
        Loki[Loki Logs Tool]
    end

    WebUI --> API
    WS <--> API
    API --> Orchestrator
    Orchestrator --> Agent1 & Agent2 & Agent3 & Agent4 & Agent5 & Agent6
    Orchestrator --> RAG
    
    %% DB State
    API & Orchestrator --> DB
    
    %% Tool execution
    Agent1 --> Loki
    Agent2 --> Prom
    Agent3 --> K8s
    Agent5 --> K8s
    Agent6 --> K8s & Prom
```

---

## 🤖 Dynamic Swarm Coordination Lifecycle

```mermaid
sequenceDiagram
    autonumber
    participant Alert as Alarm Gateway (Prometheus)
    participant Orchestrator as Agentic Orchestrator
    participant Swarm as Worker Agents
    participant Memory as Episodic memory (RAG)
    participant Human as Human-in-the-Loop Gatekeeper

    Alert->>Orchestrator: Ingest Outage Signal
    activate Orchestrator
    Orchestrator->>Memory: Query past incidents & verified fixes
    Memory-->>Orchestrator: Return context keys & fix logs
    
    rect rgb(240, 240, 240)
        Note over Orchestrator, Swarm: Parallel Task Execution
        Orchestrator->>Swarm: [Task 1] Logs Agent: Query error signatures via Loki
        Orchestrator->>Swarm: [Task 2] Metrics Agent: Fetch timeseries trends
        Orchestrator->>Swarm: [Task 3] Workload Agent: Inspect K8s container state
    end

    Swarm-->>Orchestrator: Append structured task findings to Workspace
    Orchestrator->>Swarm: [Task 4] Root Cause Analyzer: Correlate logs + metrics findings
    Swarm-->>Orchestrator: Identify Root Cause & recommend rollback/restart
    
    Orchestrator->>Swarm: [Task 5] Remediation Agent: Propose action schema
    Swarm-->>Orchestrator: Proposes JSON patch

    %% Human in the loop gate
    Orchestrator->>Human: Request approval to execute tool mutations
    Human-->>Orchestrator: Approve / Reject

    Orchestrator->>Swarm: [Task 6] Remediation Agent: Execute tool mutations
    Swarm->>Orchestrator: Mutations complete
    
    Orchestrator->>Swarm: [Task 7] Verification Agent: Audit system health post-fix
    Swarm-->>Orchestrator: System restored (Heartbeats green)
    
    Orchestrator->>Memory: Index incident context & save postmortem
    deactivate Orchestrator
```

---

## 📂 Project Directory structure

```text
aire/
├── backend/
│   ├── main.py              # API Gateway, WebSocket events, static dashboard server
│   ├── core/
│   │   ├── config.py        # System configurations & model identifiers
│   │   ├── security.py      # RBAC authorizations, prompt injection filters, secrets redaction
│   │   └── models.py        # SQLAlchemy schema mappings & state checkpoints
│   ├── agents/
│   │   ├── orchestrator.py  # Thread-safe agent context coordinator
│   │   ├── swarm.py         # Swarm workers (Logs, Metrics, Root Cause, Remediation)
│   │   └── tools.py         # Unified Tool Call Registry
│   ├── memory/
│   │   ├── rag.py           # Hybrid episodic memory search and lookup
│   │   └── episodic.py      # Long-term memory stores
│   ├── simulation/
│   │   ├── mock_services.py # Mock metrics and pod status generators
│   │   └── incident_generator.py # simulated outage scenarios
│   ├── evaluation/
│   │   └── evaluator.py     # Accuracy, precision, and faithfulness evaluations
│   └── tests/
│       └── test_sre.py      # Pytest suite verifying WAL checkpoints and rate limits
├── frontend/
│   ├── index.html           # Dark glassmorphic workflow telemetry dashboard
│   ├── style.css            # Dark variables and responsive layouts
│   └── app.js               # Websocket live listeners & action handlers
├── docs/                    # Evolved System Engineering specs directory
│   ├── architecture/        # ARCHITECTURE.md spec sheet
│   ├── ai/                  # PROMPT_ENGINEERING.md evaluation logs
│   ├── security/            # SECURITY.md threat models
│   └── adr/                 # Architectural Decision Records (ADR 001 - 003)
└── README.md                # Global documentation index
```

---

## 🛠️ Setup & Execution

### 1. Installation
Install core requirements:
```bash
pip install fastapi uvicorn pydantic-settings sqlalchemy slowapi pytest httpx
```

### 2. Start the Backend API & Server
Run the following command in the project directory:
```bash
python -m backend.main
```

### 3. Open the Telemetry Dashboard
Open your browser and navigate to:
**`http://127.0.0.1:8080/`**
*(The FastAPI server automatically serves the dashboard index assets).*

### 4. Running the Pytest Suite
Execute automated database concurrency, rate-limiter, and agent lifecycle checks:
```bash
python -m pytest backend/tests/test_sre.py
```
