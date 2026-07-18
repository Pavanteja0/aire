import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import List, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.core.config import settings
from backend.core.models import Incident, IncidentStatus, IncidentSeverity
from backend.core.security import security_manager, Role, Action
from backend.simulation.mock_services import sre_env
from backend.simulation.incident_generator import incident_generator
from backend.agents.orchestrator import orchestrator

# Configure logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("aire.main")

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
        # Convert datetime objects to string in broadcast message
        payload = json.dumps(message, default=str)
        await asyncio.gather(*[
            conn.send_text(payload) for conn in self.active_connections
        ], return_exceptions=True)

manager = ConnectionManager()

# Setup orchestrator broadcast listener to feed the WebSockets
def orchestrator_broadcast_listener(event_type: str, data: dict):
    # Run the broadcast inside the event loop safely
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
                # If incident is not already tracked in the orchestrator
                if incident.id not in orchestrator.active_incidents:
                    # Broadcast new incident detection to UI
                    await manager.broadcast({"event": "incident_detected", "data": incident.dict()})
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

# Enable CORS for frontend dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Gateway Routes ---

@app.get("/api/incidents", response_model=List[Incident])
async def list_incidents():
    """Lists all active and resolved incidents."""
    return list(orchestrator.active_incidents.values())

@app.get("/api/incidents/{incident_id}", response_model=Incident)
async def get_incident(incident_id: str):
    """Retrieves detailed information for an incident."""
    if incident_id not in orchestrator.active_incidents:
        raise HTTPException(status_code=404, detail="Incident not found")
    return orchestrator.active_incidents[incident_id]

@app.post("/api/incidents/trigger")
async def trigger_incident(incident_type: str):
    """
    Manually triggers a synthetic outage incident.
    Allowed types: 'pod_crash', 'db_leak', 'slow_auth', 'canary_failed'
    """
    # Security prompt injection validation
    if security_manager.detect_prompt_injection(incident_type):
        raise HTTPException(status_code=400, detail="Prompt Injection Detected in request parameters")

    incident = incident_generator.trigger_incident(incident_type)
    if not incident:
        raise HTTPException(status_code=400, detail=f"Invalid incident type: {incident_type}")
        
    # Start investigation async
    asyncio.create_task(orchestrator.start_investigation(incident))
    return {"status": "triggered", "incident_id": incident.id}

@app.post("/api/incidents/{incident_id}/approve")
async def approve_remediation(incident_id: str, actor: str = "LeadSRE"):
    """
    SRE Lead approval gate for proposed remediation.
    """
    if incident_id not in orchestrator.active_incidents:
        raise HTTPException(status_code=404, detail="Incident not found")
        
    # Enforce RBAC
    authorized = security_manager.authorize(
        actor=actor,
        role=Role.SRE_LEAD,
        action=Action.APPROVE_FIX,
        target=incident_id
    )
    
    if not authorized:
        raise HTTPException(status_code=403, detail="Unauthorized action role permissions mismatch")
        
    incident = orchestrator.active_incidents[incident_id]
    if incident.status != IncidentStatus.IDENTIFIED:
        raise HTTPException(status_code=400, detail="Remediation cannot be executed yet. Incident state must be IDENTIFIED.")
        
    # Launch remediation async
    asyncio.create_task(orchestrator.execute_remediation(incident_id))
    return {"status": "remediation_approved", "incident_id": incident_id}

@app.get("/api/postmortems")
async def list_postmortems():
    """Fetches all postmortems compiled by the Postmortem agent."""
    return list(orchestrator.postmortems.values())

@app.get("/api/evaluations")
async def list_evaluations():
    """Returns evaluation ratings, token cost logs, and groundedness ratings."""
    return orchestrator.evaluations

@app.get("/api/security/audit")
async def get_security_audit():
    """Retrieves SRE platform security boundary audit logs."""
    return security_manager.audit_log

@app.post("/api/environment/reset")
async def reset_environment():
    """Resets simulated environment back to completely healthy baseline."""
    sre_env.clear_outages()
    orchestrator.active_incidents.clear()
    return {"status": "environment_restored_healthy"}

# --- WebSocket Telemetry Endpoint ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial state dump
        state = {
            "incidents": [inc.dict() for inc in orchestrator.active_incidents.values()],
            "postmortems": [pm.dict() for pm in orchestrator.postmortems.values()],
            "evaluations": [ev.dict() for ev in orchestrator.evaluations],
            "audit_logs": security_manager.audit_log
        }
        # Safely serialize dates to strings
        await websocket.send_text(json.dumps({"event": "init_state", "data": state}, default=str))
        
        while True:
            # Keep connection open, handle client requests if any
            data = await websocket.receive_text()
            logger.info(f"WebSocket incoming command: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
