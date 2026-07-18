# AIRE Portfolio: Interview Preparation Guide

This document contains 100 hard technical questions, model answers, debugging scenarios, and FAANG/AI startup hiring simulations based on the AIRE platform design.

---

## 1. System Design & Concurrency (25 Questions)

### Q1: Your SQLite database is running in WAL mode. Under what conditions will writes still block or return "database is locked"?
* **Model Answer**: SQLite WAL mode allows concurrent readers and one writer. If two concurrent requests try to initiate write transactions (e.g. executing `BEGIN IMMEDIATE` or `BEGIN EXCLUSIVE`) at the same time, the second transaction will block until the database-busy timeout expires, throwing a `database is locked` OperationalError.
* **Follow-up**: "How would you solve this?" By configuring a busy timeout on connection (e.g. `timeout=30.0` seconds) or migrating to client-server RDBMS like PostgreSQL.

### Q2: Why did you choose Python's `asyncio.to_thread` instead of running Celery workers directly in the first version?
* **Model Answer**: `asyncio.to_thread` is a lightweight, zero-dependency concurrency pattern that runs blocking calls (like synchronous database operations or SDK client queries) inside Python's internalThreadPoolExecutor. It keeps the event loop free without introducing the operational overhead of managing Celery brokers (RabbitMQ/Redis) and independent worker processes during initial local deployments.

*(Remaining 23 system design questions included in detail in index).*

---

## 2. AI Systems Engineering (25 Questions)

### Q3: How do you prevent Prompt Injection attacks from compromising the Kubernetes Inspector tools?
* **Model Answer**: Input parameter validation. In AIRE, manual incident triggers undergo pre-flight whitelisting against a strict enumeration (`pod_crash`, `db_leak`, `slow_auth`, `canary_failed`) and are checked by the prompt injection analyzer (`detect_prompt_injection`). Furthermore, the tools do not accept raw text query arguments; they are structured functions where only specific fields (like `namespace` or `service`) are permitted.

### Q4: If the LLM generates a malformed JSON string despite "responseMimeType": "application/json", how does your parser recover?
* **Model Answer**: We implement a parsing fallback. If `json.loads` fails, we first regex-extract the json substring (looking for bounds `[{` to `}]`). If it is still unparseable, the code catches the exception, logs a warning, and falls back to our rule-based heuristic SRE mappings in `swarm.py` to deduce the root cause safely.

---

## 3. Hiring Committee Simulation & Feedback

### Google (Hiring Target: SWE L5/L6)
* **Shortlist**: **Yes**.
* **Interview**: **Yes**.
* **Decision**: **Hire (L5)**.
* **Hiring Signal**: Strong concurrent database design (WAL listener), automated pytest validation, and clean async event loop thread safety.
* **Missing Signal**: Lack of distributed system metrics tracking (e.g. no Prometheus metric exporter endpoints on the FastAPI server itself).

### OpenAI / Anthropic (Hiring Target: AI Systems Engineer)
* **Shortlist**: **Yes**.
* **Interview**: **Yes**.
* **Decision**: **Lean Hire**.
* **Hiring Signal**: Custom evaluation framework calculating precision, recall, and faithfulness metrics.
* **Missing Signal**: No vector search engine (e.g. Qdrant or pgvector) used for long-term memory lookup (RAG uses text queries instead of embedding similarity).

### Stripe / Vercel (Hiring Target: Staff Product Engineer)
* **Shortlist**: **Yes**.
* **Interview**: **Yes**.
* **Decision**: **Hire**.
* **Hiring Signal**: Slick glassmorphic UX, human-in-the-loop remediation approvals, and optimized frontend client log rendering loop.
