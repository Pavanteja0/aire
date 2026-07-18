from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import json

# SQLAlchemy Imports
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, DateTime, Text, ForeignKey, event
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.engine import Engine
from backend.core.config import settings

# Enums
class IncidentSeverity(str, Enum):
    SEV1 = "SEV1"  # Critical outage, customer-facing downtime
    SEV2 = "SEV2"  # Partial degradation, high latency or elevated error rates
    SEV3 = "SEV3"  # Minor degradation, non-blocking operational issues

class IncidentStatus(str, Enum):
    DETECTED = "DETECTED"
    INVESTIGATING = "INVESTIGATING"
    IDENTIFIED = "IDENTIFIED"
    REMEDIATING = "REMEDIATING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"

# Pydantic Schemas (FastAPI & Agent Swarm Contracts)
class LogEntry(BaseModel):
    timestamp: datetime
    service: str
    level: str
    message: str
    pod_name: Optional[str] = None
    trace_id: Optional[str] = None

class MetricPoint(BaseModel):
    timestamp: datetime
    value: float

class TimeSeries(BaseModel):
    metric_name: str
    labels: Dict[str, str] = Field(default_factory=dict)
    values: List[MetricPoint] = Field(default_factory=list)

class KubernetesPod(BaseModel):
    name: str
    namespace: str
    status: str  # Running, CrashLoopBackOff, Pending, Terminating
    restarts: int
    cpu_usage_cores: float
    memory_usage_bytes: int
    node_name: str
    created_at: datetime
    last_state_terminated_reason: Optional[str] = None

class DeploymentInfo(BaseModel):
    service_name: str
    current_version: str
    previous_version: str
    status: str  # Deployed, Failed, RollingBack
    deployed_at: datetime
    commit_sha: str
    changelog: str
    ci_cd_status: str  # Success, Failed, Running

class AgentTaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class AgentTask(BaseModel):
    id: str
    agent_name: str
    status: AgentTaskStatus = AgentTaskStatus.PENDING
    description: str
    findings: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)

class Incident(BaseModel):
    id: str
    title: str
    description: str
    severity: IncidentSeverity
    status: IncidentStatus = IncidentStatus.DETECTED
    service: str
    created_at: datetime = Field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    detected_by: str  # PrometheusAlert, Manual, LogsAnomaly
    
    # State tracking during investigation
    tasks: List[AgentTask] = Field(default_factory=list)
    root_cause: Optional[str] = None
    proposed_remediation: Optional[str] = None
    remediation_executed: bool = False
    verification_passed: Optional[bool] = None
    postmortem_id: Optional[str] = None

class IncidentPostmortem(BaseModel):
    id: str
    incident_id: str
    title: str
    severity: IncidentSeverity
    service: str
    created_at: datetime
    resolved_at: datetime
    owner: str = "AIRE Agent Swarm"
    executive_summary: str
    timeline: List[Dict[str, Any]] = Field(default_factory=list)  # [{timestamp, event}]
    trigger: str
    root_cause: str
    remediation_details: str
    action_items: List[str] = Field(default_factory=list)
    preventative_measures: List[str] = Field(default_factory=list)

class EvaluationMetric(BaseModel):
    run_id: str
    incident_id: str
    incident_type: str
    precision: float  # Relevant actions / total actions
    recall: float     # Target findings found / total target findings
    faithfulness: float  # Grounded in logs/metrics
    hallucination_rate: float
    latency_seconds: float
    token_cost_usd: float
    human_rating: Optional[int] = None  # 1-5 scale
    timestamp: datetime = Field(default_factory=datetime.now)


# ==========================================
# SQL ORM Persistence Engine Definitions
# ==========================================
Base = declarative_base()

class SQLIncident(Base):
    __tablename__ = "incidents"
    
    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(String, nullable=False)
    status = Column(String, default="DETECTED")
    service = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    detected_by = Column(String, nullable=False)
    
    root_cause = Column(Text, nullable=True)
    proposed_remediation = Column(Text, nullable=True)
    remediation_executed = Column(Boolean, default=False)
    verification_passed = Column(Boolean, nullable=True)
    postmortem_id = Column(String, nullable=True)
    
    # Cascade deletes tasks when an incident is deleted
    tasks = relationship("SQLAgentTask", back_populates="incident", cascade="all, delete-orphan")


class SQLAgentTask(Base):
    __tablename__ = "agent_tasks"
    
    id = Column(String, primary_key=True, index=True)
    incident_id = Column(String, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False)
    agent_name = Column(String, nullable=False)
    status = Column(String, default="PENDING")
    description = Column(Text, nullable=False)
    findings = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    tool_calls = Column(Text, default="[]") # Saved as JSON stringified array
    
    incident = relationship("SQLIncident", back_populates="tasks")


class SQLIncidentPostmortem(Base):
    __tablename__ = "postmortems"
    
    id = Column(String, primary_key=True, index=True)
    incident_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    service = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=False)
    owner = Column(String, default="AIRE Agent Swarm")
    executive_summary = Column(Text, nullable=False)
    timeline = Column(Text, default="[]") # Saved as JSON stringified timeline
    trigger = Column(Text, nullable=False)
    root_cause = Column(Text, nullable=False)
    remediation_details = Column(Text, nullable=False)
    action_items = Column(Text, default="[]") # Saved as JSON stringified list
    preventative_measures = Column(Text, default="[]") # Saved as JSON stringified list


class SQLEvaluationMetric(Base):
    __tablename__ = "evaluations"
    
    run_id = Column(String, primary_key=True, index=True)
    incident_id = Column(String, nullable=False)
    incident_type = Column(String, nullable=False)
    precision = Column(Float, nullable=False)
    recall = Column(Float, nullable=False)
    faithfulness = Column(Float, nullable=False)
    hallucination_rate = Column(Float, nullable=False)
    latency_seconds = Column(Float, nullable=False)
    token_cost_usd = Column(Float, nullable=False)
    human_rating = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


class SQLAuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False)
    target = Column(String, nullable=False)
    status = Column(String, nullable=False)
    details = Column(Text, nullable=False)


# Connection Engine Setup
engine = create_engine(
    f"sqlite:///{settings.DB_PATH}",
    connect_args={"check_same_thread": False}
)

# Concurrency & WAL mode enforcer
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        db.execute(Base.metadata.create_all(bind=engine))
        yield db
    finally:
        db.close()

# ORM Model Mapping & Persistence Helpers
def sql_to_pydantic_incident(sql_inc: SQLIncident) -> Incident:
    tasks = []
    for t in sql_inc.tasks:
        tasks.append(AgentTask(
            id=t.id,
            agent_name=t.agent_name,
            status=AgentTaskStatus(t.status),
            description=t.description,
            findings=t.findings,
            started_at=t.started_at,
            completed_at=t.completed_at,
            tool_calls=json.loads(t.tool_calls) if t.tool_calls else []
        ))
    return Incident(
        id=sql_inc.id,
        title=sql_inc.title,
        description=sql_inc.description or "",
        severity=IncidentSeverity(sql_inc.severity),
        status=IncidentStatus(sql_inc.status),
        service=sql_inc.service,
        created_at=sql_inc.created_at,
        resolved_at=sql_inc.resolved_at,
        detected_by=sql_inc.detected_by,
        tasks=tasks,
        root_cause=sql_inc.root_cause,
        proposed_remediation=sql_inc.proposed_remediation,
        remediation_executed=sql_inc.remediation_executed,
        verification_passed=sql_inc.verification_passed,
        postmortem_id=sql_inc.postmortem_id
    )

def save_incident_to_db(incident: Incident):
    db = SessionLocal()
    try:
        sql_inc = db.query(SQLIncident).filter(SQLIncident.id == incident.id).first()
        if not sql_inc:
            sql_inc = SQLIncident(
                id=incident.id,
                title=incident.title,
                description=incident.description,
                severity=incident.severity.value,
                status=incident.status.value,
                service=incident.service,
                created_at=incident.created_at,
                resolved_at=incident.resolved_at,
                detected_by=incident.detected_by
            )
            db.add(sql_inc)
        else:
            sql_inc.status = incident.status.value
            sql_inc.resolved_at = incident.resolved_at
            sql_inc.root_cause = incident.root_cause
            sql_inc.proposed_remediation = incident.proposed_remediation
            sql_inc.remediation_executed = incident.remediation_executed
            sql_inc.verification_passed = incident.verification_passed
            sql_inc.postmortem_id = incident.postmortem_id

        for task in incident.tasks:
            sql_task = db.query(SQLAgentTask).filter(SQLAgentTask.id == task.id).first()
            if not sql_task:
                sql_task = SQLAgentTask(
                    id=task.id,
                    incident_id=incident.id,
                    agent_name=task.agent_name,
                    status=task.status.value,
                    description=task.description,
                    findings=task.findings,
                    started_at=task.started_at,
                    completed_at=task.completed_at,
                    tool_calls=json.dumps(task.tool_calls)
                )
                db.add(sql_task)
            else:
                sql_task.status = task.status.value
                sql_task.findings = task.findings
                sql_task.completed_at = task.completed_at
                sql_task.tool_calls = json.dumps(task.tool_calls)
        db.commit()
    finally:
        db.close()

def save_postmortem_to_db(pm: IncidentPostmortem):
    db = SessionLocal()
    try:
        sql_pm = db.query(SQLIncidentPostmortem).filter(SQLIncidentPostmortem.id == pm.id).first()
        if not sql_pm:
            sql_pm = SQLIncidentPostmortem(
                id=pm.id,
                incident_id=pm.incident_id,
                title=pm.title,
                severity=pm.severity.value,
                service=pm.service,
                created_at=pm.created_at,
                resolved_at=pm.resolved_at,
                owner=pm.owner,
                executive_summary=pm.executive_summary,
                timeline=json.dumps(pm.timeline),
                trigger=pm.trigger,
                root_cause=pm.root_cause,
                remediation_details=pm.remediation_details,
                action_items=json.dumps(pm.action_items),
                preventative_measures=json.dumps(pm.preventative_measures)
            )
            db.add(sql_pm)
        else:
            sql_pm.incident_id = pm.incident_id
            sql_pm.title = pm.title
            sql_pm.severity = pm.severity.value
            sql_pm.service = pm.service
            sql_pm.resolved_at = pm.resolved_at
            sql_pm.executive_summary = pm.executive_summary
            sql_pm.timeline = json.dumps(pm.timeline)
            sql_pm.trigger = pm.trigger
            sql_pm.root_cause = pm.root_cause
            sql_pm.remediation_details = pm.remediation_details
            sql_pm.action_items = json.dumps(pm.action_items)
            sql_pm.preventative_measures = json.dumps(pm.preventative_measures)
        db.commit()
    finally:
        db.close()

def save_evaluation_to_db(ev: EvaluationMetric):
    db = SessionLocal()
    try:
        sql_ev = db.query(SQLEvaluationMetric).filter(SQLEvaluationMetric.run_id == ev.run_id).first()
        if not sql_ev:
            sql_ev = SQLEvaluationMetric(
                run_id=ev.run_id,
                incident_id=ev.incident_id,
                incident_type=ev.incident_type,
                precision=ev.precision,
                recall=ev.recall,
                faithfulness=ev.faithfulness,
                hallucination_rate=ev.hallucination_rate,
                latency_seconds=ev.latency_seconds,
                token_cost_usd=ev.token_cost_usd,
                human_rating=ev.human_rating,
                timestamp=ev.timestamp
            )
            db.add(sql_ev)
        else:
            sql_ev.incident_id = ev.incident_id
            sql_ev.incident_type = ev.incident_type
            sql_ev.precision = ev.precision
            sql_ev.recall = ev.recall
            sql_ev.faithfulness = ev.faithfulness
            sql_ev.hallucination_rate = ev.hallucination_rate
            sql_ev.latency_seconds = ev.latency_seconds
            sql_ev.token_cost_usd = ev.token_cost_usd
            sql_ev.human_rating = ev.human_rating
            sql_ev.timestamp = ev.timestamp
        db.commit()
    finally:
        db.close()

def save_audit_log_to_db(actor: str, action: str, target: str, status: str, details: str):
    db = SessionLocal()
    try:
        sql_log = SQLAuditLog(
            timestamp=datetime.utcnow(),
            actor=actor,
            action=action,
            target=target,
            status=status,
            details=details
        )
        db.add(sql_log)
        db.commit()
    finally:
        db.close()

