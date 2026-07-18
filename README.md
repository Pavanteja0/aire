# AIRE: Autonomous Incident Response Engineer

AIRE is a production-grade, highly autonomous Site Reliability Engineering (SRE) platform. It behaves like an experienced SRE at scale, detecting outages, correlating logs/metrics, inspecting simulated Kubernetes workloads, executing safe remediations, drafting postmortems, and continuously learning from past failures.

## 🏛️ System Architecture

```mermaid
graph TD
    subgraph Client Layer
        WebUI[React/HTML5 Dashboard]
        WS[WebSocket Live Timeline]
    end

    subgraph API Gateway & Control Plane
        API[FastAPI Gateway]
        Auth[RBAC & Policy Engine]
        DB[(SQLite / PostgreSQL)]
    end

    subgraph Agent Swarm Orchestrator
        Planner[Planner Agent]
        Router[Task Router & Msg Bus]
        ShortTerm[(Short-Term Workspace)]
    end

    subgraph Worker Swarm
        Agent1[Log Investigator]
        Agent2[Metrics Investigator]
        Agent3[Kubernetes Inspector]
        Agent4[Root Cause Analyzer]
        Agent5[Remediation Agent]
        Agent6[Verification Agent]
    end

    subgraph Target Environments [Simulated Infrastructure]
        K8s[Kubernetes API]
        Prom[Prometheus Metrics]
        Loki[Loki Logs]
        Git[GitHub Deployments]
        PD[PagerDuty / Slack]
    end

    subgraph Advanced Memory & RAG
        VecDB[(Vector DB: FAISS/Chroma)]
        GraphDB[(Graph RAG: Topology)]
        LongTerm[(Episodic Memory)]
    end

    WebUI --> API
    WS <--> API
    API --> Planner
    Planner --> Router
    Router --> Agent1 & Agent2 & Agent3 & Agent4 & Agent5 & Agent6
    
    %% Tool Queries
    Agent1 --> Loki
    Agent2 --> Prom
    Agent3 --> K8s
    Agent5 --> Git
    Agent6 --> K8s & Prom
    
    %% RAG & Memory
    Planner & Agent4 --> VecDB & GraphDB & LongTerm
    
    %% DB State
    API & Planner --> DB
```

---

## 🤖 Collaborative Agent Swarm Flow

Rather than a simple sequential pipeline, AIRE implements an **asynchronous event-driven agent swarm**. The **Planner Agent** acts as the dispatcher, dividing the problem into structured sub-tasks and routing them via a task-status state machine.

```mermaid
sequenceDiagram
    autonumber
    participant Alert as Prometheus Alerting
    participant Planner as SRE Planner Agent
    participant Swarm as Worker Agents
    participant Memory as Long-Term Episodic Memory
    participant Human as SRE Operator (Human-in-the-Loop)

    Alert->>Planner: Trigger Alert (e.g. SEV1: payment-service latency spike)
    activate Planner
    Planner->>Memory: Query past incidents for "payment-service latency"
    Memory-->>Planner: Return past solutions (e.g. "restarted payment-db pod")
    
    rect rgb(240, 240, 240)
        Note over Planner, Swarm: Parallel Investigation
        Planner->>Swarm: [Task 1] Metrics Agent: Fetch API latency & error rates
        Planner->>Swarm: [Task 2] Logs Agent: Query error traces in payment-service
        Planner->>Swarm: [Task 3] K8s Agent: Check container restarts & CPU limits
    end

    Swarm-->>Planner: Returns correlated logs, metrics & pod restart evidence
    Planner->>Swarm: [Task 4] Root Cause Analyzer: Correlate evidence and past postmortems
    Swarm-->>Planner: Root Cause identified (DB connection pool exhaustion due to traffic)
    
    Planner->>Swarm: [Task 5] Remediation Agent: Propose fix (Scale replicas & restart DB pod)
    Swarm-->>Planner: Remediation Proposed

    %% Human in the loop gate
    Planner->>Human: Request approval to execute remediation
    Human-->>Planner: Approved

    Planner->>Swarm: [Task 6] Remediation Agent: Execute remediation
    Swarm->>Planner: Remediation completed
    
    Planner->>Swarm: [Task 7] Verification Agent: Run regression checks on metrics
    Swarm-->>Planner: Verified (Latency < 50ms, error rate 0%)
    
    Planner->>Memory: Index incident and write postmortem
    deactivate Planner
```

---

## 📂 Project Directory Structure

```text
aire/
├── backend/
│   ├── main.py              # FastAPI entrypoint, websocket handlers
│   ├── core/
│   │   ├── config.py        # Global settings, security redaction parameters
│   │   ├── security.py      # RBAC, injection filters, human approval gates
│   │   └── models.py        # Typed Pydantic data schemas
│   ├── agents/
│   │   ├── orchestrator.py  # SRE Planner Agent logic
│   │   ├── swarm.py         # Sub-agents (Logs, Metrics, Root Cause, Remediation)
│   │   └── tools.py         # SRE Client APIs (Prometheus, Loki, K8s, GitHub)
│   ├── memory/
│   │   ├── rag.py           # Hybrid & Graph RAG implementation
│   │   └── episodic.py      # Past incident memory recall
│   ├── simulation/
│   │   ├── mock_services.py # Mock timeseries data & pod container status generators
│   │   └── incident_generator.py # Simulators for PodCrash, LatencySpike, CanaryFailed
│   ├── evaluation/
│   │   └── evaluator.py     # Golden dataset scoring & performance evaluation
│   └── tests/               # Pytest suite
├── frontend/
│   ├── index.html           # Glassmorphic central dashboard UI
│   ├── style.css            # Dark variables, transitions, layouts
│   └── app.js               # Event-based Websocket updates
└── README.md                # System design & Documentation hub
```

---

## 🛠️ Setup & Running

Instructions on running the backend server and dashboard locally:

1. **Install requirements**:
   ```bash
   pip install fastapi uvicorn pydantic-settings jinja2 pytest
   ```
2. **Start the backend control plane**:
   ```bash
   python backend/main.py
   ```
3. **Open the frontend**:
   Open `frontend/index.html` in your browser to view the real-time agent dashboard.
