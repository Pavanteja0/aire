from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

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
