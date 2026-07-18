# ADR 001: Local-First Persistent Database Selection

## Status
Approved

## Context
The AIRE SRE control plane requires a database to store incidents, tasks, evaluations, audit logs, and postmortem records. The design must support concurrent multi-agent writes while maintaining a frictionless, zero-dependency local development setup for candidates and engineers evaluating the portfolio.

## Decisions Considered
1. **PostgreSQL / MySQL**: Requires launching secondary Docker containers or running local server daemons.
2. **In-Memory RAM Dicts**: Simple, but data is lost on server restart, preventing the orchestrator from recovering incident state after process reboots.
3. **SQLite with Write-Ahead Logging (WAL)**: File-based database requiring zero setup, with concurrency optimizations to support parallel agent writes.

## Decision
We chose **SQLite with SQLAlchemy ORM + Write-Ahead Logging (WAL) enabled**.

## Consequences
* **Pros**:
  * Zero-install developer experience: SQLite is included in the Python standard library.
  * State durability: If the uvicorn server restarts, the orchestrator syncs with the database file to restore active workflows.
  * Concurrency support: WAL mode allows concurrent reads and writes without file locks.
* **Cons**:
  * Cannot scale horizontally to multiple server processes without distributed file storage. (Mitigation documented in `docs/system_design/SYSTEM_DESIGN.md`).
