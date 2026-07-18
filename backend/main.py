import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import List, Set
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from backend.core.config import settings
from backend.core.models import (
    Incident, IncidentStatus, IncidentSeverity, SessionLocal, SQLIncident, SQLAgentTask,
    SQLIncidentPostmortem, SQLEvaluationMetric, SQLAuditLog, save_audit_log_to_db, sql_to_pydantic_incident, init_db
)
from backend.core.security import security_manager, Role, Action
from backend.simulation.mock_services import sre_env
from backend.simulation.incident_generator import incident_generator
from backend.agents.orchestrator import orchestrator

# Configure logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("aire.main")

# Rate Limiter Setup
limiter = Limiter(key_func=get_remote_address)

# Track active WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Active connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        payload = json.dumps(message, default=str)
        await asyncio.gather(*[
            conn.send_text(payload) for conn in self.active_connections
        ], return_exceptions=True)

manager = ConnectionManager()

# Setup orchestrator broadcast listener to feed the WebSockets
def orchestrator_broadcast_listener(event_type: str, data: dict):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(manager.broadcast({"event": event_type, "data": data}))
    except Exception as e:
        logger.error(f"Failed to broadcast orchestrator event {event_type}: {e}")

orchestrator.register_listener(orchestrator_broadcast_listener)

async def simulation_ticker_loop():
    """
    Background simulation ticker. Ticks the SRE environment,
    checks alert thresholds, and boots investigations.
    """
    logger.info("Simulation ticker background task started.")
    try:
        while True:
            # Tick the environment
            sre_env.tick()
            
            # Check thresholds for new alerts
            new_incidents = incident_generator.check_thresholds()
            for incident in new_incidents:
                # Check if tracked in memory or DB
                if incident.id not in orchestrator.active_incidents:
                    # Broadcast new incident detection to UI
                    await manager.broadcast({"event": "incident_detected", "data": incident.model_dump()})
                    # Start async investigation
                    asyncio.create_task(orchestrator.start_investigation(incident))
                    
            await asyncio.sleep(settings.SIMULATION_TICK_RATE_SEC)
    except asyncio.CancelledError:
        logger.info("Simulation ticker background task stopped.")
    except Exception as e:
        logger.error(f"Error in simulation ticker loop: {e}", exc_info=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    ticker_task = asyncio.create_task(simulation_ticker_loop())
    yield
    # Shutdown
    ticker_task.cancel()
    try:
        await ticker_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="AIRE: Autonomous Incident Response Engineer Platform",
    version="1.0.0",
    lifespan=lifespan
)

# Wire Rate Limiting handlers
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Enable CORS for frontend dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Health Check Routes ---
@app.get("/healthz")
@app.get("/readyz")
async def health_check():
    """Liveness and readiness probes for load balancers."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

# --- API Gateway Routes ---
@app.get("/api/incidents", response_model=List[Incident])
async def list_incidents():
    """Lists all active and resolved incidents from database."""
    db = SessionLocal()
    try:
        sql_incs = db.query(SQLIncident).all()
        # Refresh memory cache
        for si in sql_incs:
            orchestrator.active_incidents[si.id] = sql_to_pydantic_incident(si)
        return list(orchestrator.active_incidents.values())
    finally:
        db.close()

@app.get("/api/incidents/{incident_id}", response_model=Incident)
async def get_incident(incident_id: str):
    """Retrieves detailed information for an incident from database."""
    db = SessionLocal()
    try:
        si = db.query(SQLIncident).filter(SQLIncident.id == incident_id).first()
        if not si:
            raise HTTPException(status_code=404, detail="Incident not found")
        pydantic_inc = sql_to_pydantic_incident(si)
        orchestrator.active_incidents[incident_id] = pydantic_inc
        return pydantic_inc
    finally:
        db.close()

@app.post("/api/incidents/trigger")
@limiter.limit("10/minute")
async def trigger_incident(incident_type: str, request: Request):
    """
    Manually triggers a synthetic outage incident.
    Allowed types: 'pod_crash', 'db_leak', 'slow_auth', 'canary_failed'
    """
    # Parameter Sanitization & Whitelisting
    allowed_types = {"pod_crash", "db_leak", "slow_auth", "canary_failed"}
    if incident_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Unsupported incident trigger parameter: {incident_type}")

    # Security prompt injection validation
    if security_manager.detect_prompt_injection(incident_type):
        raise HTTPException(status_code=400, detail="Prompt Injection Detected in request parameters")

    incident = incident_generator.trigger_incident(incident_type)
    if not incident:
        raise HTTPException(status_code=400, detail=f"Failed to generate incident for type: {incident_type}")
        
    save_audit_log_to_db("LeadSRE", "trigger_incident", incident.id, "APPROVED", f"Manual trigger of {incident_type} scenario.")
        
    # Start investigation async
    asyncio.create_task(orchestrator.start_investigation(incident))
    return {"status": "triggered", "incident_id": incident.id}

@app.post("/api/incidents/{incident_id}/approve")
async def approve_remediation(incident_id: str, actor: str = "LeadSRE"):
    """
    SRE Lead approval gate for proposed remediation.
    """
    # Enforce RBAC
    authorized = security_manager.authorize(
        actor=actor,
        role=Role.SRE_LEAD,
        action=Action.APPROVE_FIX,
        target=incident_id
    )
    
    if not authorized:
        raise HTTPException(status_code=403, detail="Unauthorized action role permissions mismatch")
        
    db = SessionLocal()
    try:
        si = db.query(SQLIncident).filter(SQLIncident.id == incident_id).first()
        if not si:
            raise HTTPException(status_code=404, detail="Incident not found")
        incident = sql_to_pydantic_incident(si)
        orchestrator.active_incidents[incident_id] = incident
    finally:
        db.close()
        
    if incident.status != IncidentStatus.IDENTIFIED:
        raise HTTPException(status_code=400, detail="Remediation cannot be executed yet. Incident state must be IDENTIFIED.")
        
    # Launch remediation async
    asyncio.create_task(orchestrator.execute_remediation(incident_id))
    return {"status": "remediation_approved", "incident_id": incident_id}

@app.get("/api/postmortems")
async def list_postmortems():
    """Fetches all postmortems compiled from the database."""
    db = SessionLocal()
    try:
        sql_pms = db.query(SQLIncidentPostmortem).all()
        pms = []
        for spm in sql_pms:
            pms.append({
                "id": spm.id,
                "incident_id": spm.incident_id,
                "title": spm.title,
                "severity": spm.severity,
                "service": spm.service,
                "created_at": spm.created_at,
                "resolved_at": spm.resolved_at,
                "owner": spm.owner,
                "executive_summary": spm.executive_summary,
                "timeline": json.loads(spm.timeline) if spm.timeline else [],
                "trigger": spm.trigger,
                "root_cause": spm.root_cause,
                "remediation_details": spm.remediation_details,
                "action_items": json.loads(spm.action_items) if spm.action_items else [],
                "preventative_measures": json.loads(spm.preventative_measures) if spm.preventative_measures else []
            })
        return pms
    finally:
        db.close()

@app.get("/api/evaluations")
async def list_evaluations():
    """Returns evaluation ratings, token cost logs, and groundedness ratings from DB."""
    db = SessionLocal()
    try:
        sql_evs = db.query(SQLEvaluationMetric).order_by(SQLEvaluationMetric.timestamp.desc()).all()
        return [
            {
                "run_id": ev.run_id,
                "incident_id": ev.incident_id,
                "incident_type": ev.incident_type,
                "precision": ev.precision,
                "recall": ev.recall,
                "faithfulness": ev.faithfulness,
                "hallucination_rate": ev.hallucination_rate,
                "latency_seconds": ev.latency_seconds,
                "token_cost_usd": ev.token_cost_usd,
                "human_rating": ev.human_rating,
                "timestamp": ev.timestamp
            } for ev in sql_evs
        ]
    finally:
        db.close()

@app.get("/api/security/audit")
async def get_security_audit():
    """Retrieves SRE platform security boundary audit logs from database."""
    db = SessionLocal()
    try:
        logs = db.query(SQLAuditLog).order_by(SQLAuditLog.timestamp.desc()).all()
        return [
            {
                "timestamp": log.timestamp.isoformat(),
                "actor": log.actor,
                "action": log.action,
                "target": log.target,
                "status": log.status,
                "details": log.details
            } for log in logs
        ]
    finally:
        db.close()

@app.post("/api/environment/reset")
async def reset_environment():
    """Resets simulated SRE environment and clears SQLite tables completely."""
    sre_env.clear_outages()
    orchestrator.active_incidents.clear()
    orchestrator.postmortems.clear()
    orchestrator.evaluations.clear()
    
    db = SessionLocal()
    try:
        db.query(SQLIncident).delete()
        db.query(SQLAgentTask).delete()
        db.query(SQLIncidentPostmortem).delete()
        db.query(SQLEvaluationMetric).delete()
        db.query(SQLAuditLog).delete()
        db.commit()
    finally:
        db.close()
        
    return {"status": "environment_restored_healthy"}

# --- WebSocket Telemetry Endpoint ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    db = SessionLocal()
    try:
        # Load state from database to initialize UI
        sql_incs = db.query(SQLIncident).all()
        sql_pms = db.query(SQLIncidentPostmortem).all()
        sql_evs = db.query(SQLEvaluationMetric).all()
        sql_audits = db.query(SQLAuditLog).order_by(SQLAuditLog.timestamp.desc()).all()
        
        incidents = [sql_to_pydantic_incident(inc).model_dump() for inc in sql_incs]
        
        postmortems = []
        for pm in sql_pms:
            postmortems.append({
                "id": pm.id,
                "incident_id": pm.incident_id,
                "title": pm.title,
                "severity": pm.severity,
                "service": pm.service,
                "created_at": pm.created_at,
                "resolved_at": pm.resolved_at,
                "owner": pm.owner,
                "executive_summary": pm.executive_summary,
                "timeline": json.loads(pm.timeline) if pm.timeline else [],
                "trigger": pm.trigger,
                "root_cause": pm.root_cause,
                "remediation_details": pm.remediation_details,
                "action_items": json.loads(pm.action_items) if pm.action_items else [],
                "preventative_measures": json.loads(pm.preventative_measures) if pm.preventative_measures else []
            })
            
        evaluations = [
            {
                "run_id": ev.run_id,
                "incident_id": ev.incident_id,
                "incident_type": ev.incident_type,
                "precision": ev.precision,
                "recall": ev.recall,
                "faithfulness": ev.faithfulness,
                "hallucination_rate": ev.hallucination_rate,
                "latency_seconds": ev.latency_seconds,
                "token_cost_usd": ev.token_cost_usd,
                "human_rating": ev.human_rating,
                "timestamp": ev.timestamp
            } for ev in sql_evs
        ]
        
        audits = [
            {
                "timestamp": log.timestamp.isoformat(),
                "actor": log.actor,
                "action": log.action,
                "target": log.target,
                "status": log.status,
                "details": log.details
            } for log in sql_audits
        ]
        
        state = {
            "incidents": incidents,
            "postmortems": postmortems,
            "evaluations": evaluations,
            "audit_logs": audits
        }
        await websocket.send_text(json.dumps({"event": "init_state", "data": state}, default=str))
        
        while True:
            data = await websocket.receive_text()
            logger.info(f"WebSocket incoming command: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}", exc_info=True)
        manager.disconnect(websocket)
    finally:
        db.close()

# Serve static frontend files on the root URL
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    # Enforce database schema initialization at entry point
    init_db()
    uvicorn.run(app, host="127.0.0.1", port=8080)
