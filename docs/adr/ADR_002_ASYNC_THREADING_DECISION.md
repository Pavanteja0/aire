# ADR 002: Async Thread Pool Delegation for Blocking SRE Tools

## Status
Approved

## Context
AIRE's API server is built on FastAPI, utilizing an asynchronous single-threaded event loop. However, SRE tools (e.g. Loki, Prometheus, Kubernetes Client SDKs) make blocking network calls. Running these directly within the async event loop blocks all other active operations, including WebSocket telemetry updates to browser clients.

## Decisions Considered
1. **Rewrite all SRE client libraries as native async**: Very expensive and complex due to lack of official async SDK support in some third-party libraries.
2. **Celery Worker offloading**: High operational overhead (requires RabbitMQ and worker processes) for local simulation runs.
3. **`asyncio.to_thread` Worker Pools**: Delegating synchronous blocking execution calls to Python's built-in background thread pool.

## Decision
We chose **`asyncio.to_thread` Worker Pools** inside the `SREOrchestrator` execution loop.

## Consequences
* **Pros**:
  * The main FastAPI event loop remains responsive and does not stutter.
  * Allows keeping the existing synchronous SRE mock client libraries without modifications.
* **Cons**:
  * Python's Global Interpreter Lock (GIL) limits CPU-bound scaling (not a bottleneck for I/O-bound SRE client HTTP queries).
