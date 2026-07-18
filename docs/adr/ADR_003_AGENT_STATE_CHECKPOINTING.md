# ADR 003: Transaction-Based Agentic State Checkpointing

## Status
Approved

## Context
In long-running agent reasoning tasks, network glitches or LLM API timeouts can interrupt workflows mid-execution. If the system crashes, the orchestrator needs to recover the exact task checkpoint (completed tasks, findings, and tool logs) to resume execution without running duplicate queries (which would incur unnecessary token costs and duplicate cluster mutations).

## Decisions Considered
1. **In-Memory State Logs**: Fast, but loses all task progress on process restarts.
2. **Periodic JSON Snapshots**: Simple, but prone to race conditions if two threads write concurrently.
3. **ORM Database Checkpoints (SQLite/Postgres)**: Every transition in the orchestrator workflow executes as an ACID database transaction immediately, updating database tables (`tasks`, `incidents`).

## Decision
We chose **ORM Database Checkpoints (SQLite/Postgres)** using SQLAlchemy session-scoped writes.

## Consequences
* **Pros**:
  * Durability: If the FastAPI container rebooted during Phase 4 (e.g. OOM), the orchestrator reads the database at startup and resumes exactly where the agent stopped.
  * Consistency: Prevent duplicate executions of SRE remediations.
* **Cons**:
  * Overhead of persistent disk I/O on every task update (offset by utilizing SQLite WAL mode andNormal synchronous writes).
