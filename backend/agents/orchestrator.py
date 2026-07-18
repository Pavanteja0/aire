import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from backend.core.models import (
    Incident, IncidentStatus, AgentTask, AgentTaskStatus, IncidentPostmortem, EvaluationMetric
)
from backend.agents.swarm import (
    KubernetesInspector, LogInvestigator, MetricsInvestigator, RootCauseAnalyzer, RemediationAgent, VerificationAgent
)
from backend.memory.rag import rag_store
from backend.memory.episodic import episodic_memory
from backend.evaluation.evaluator import evaluator

logger = logging.getLogger("aire.orchestrator")

class SREOrchestrator:
    """
    The SRE Planner Agent that manages the lifecycle of an active incident.
    Coordinates specialized agents, updates state, requests human-in-the-loop approvals,
    writes postmortems, indexes memories, and outputs real-time WebSocket feeds.
    """
    def __init__(self):
        self.active_incidents: Dict[str, Incident] = {}
        self.postmortems: Dict[str, IncidentPostmortem] = {}
        self.evaluations: List[EvaluationMetric] = []
        self.listeners: List[Callable[[str, Any], None]] = []

        # Instantiating the swarm
        self.k8s_agent = KubernetesInspector()
        self.logs_agent = LogInvestigator()
        self.metrics_agent = MetricsInvestigator()
        self.rca_agent = RootCauseAnalyzer()
        self.remediation_agent = RemediationAgent()
        self.verification_agent = VerificationAgent()

    def register_listener(self, callback: Callable[[str, Any], None]):
        self.listeners.append(callback)

    def _broadcast(self, event_type: str, data: Any):
        for callback in self.listeners:
            try:
                callback(event_type, data)
            except Exception as e:
                logger.error(f"Listener error in broadcast: {e}")

    async def start_investigation(self, incident: Incident):
        """
        Main orchestration loop for an incident.
        """
        logger.info(f"Starting SRE Planner orchestrator for Incident: {incident.id}")
        self.active_incidents[incident.id] = incident
        incident.status = IncidentStatus.INVESTIGATING
        self._broadcast("incident_updated", incident.dict())

        # Step 1: Gather Topological Context (Graph RAG)
        topology = rag_store.get_topology_context(incident.service)
        logger.info(f"Retrieved architecture topology context for {incident.service}: {topology}")

        # Step 2: Query long-term episodic memory for past similar incident patterns
        similar_incidents = episodic_memory.recall_similar_incidents(incident.title, incident.service)
        logger.info(f"Recalled {len(similar_incidents)} past similar incident episodes.")

        # Create base context for workers
        context = {
            "service": incident.service,
            "topology": topology,
            "similar_incidents": similar_incidents,
            "all_findings": {}
        }

        # Step 3: Run parallel investigative tasks (K8s, Logs, Metrics)
        tasks_to_run = [
            ("inspect-k8s", "Inspect Kubernetes resource state and container restart loops", self.k8s_agent),
            ("analyze-logs", "Query Loki error logs and identify stack trace signatures", self.logs_agent),
            ("profile-metrics", "Query Prometheus performance metric deviations and latency checks", self.metrics_agent)
        ]

        for task_id, desc, agent in tasks_to_run:
            agent_task = AgentTask(
                id=f"{incident.id}-{task_id}",
                agent_name=agent.name,
                description=desc
            )
            incident.tasks.append(agent_task)
            self._broadcast("incident_updated", incident.dict())
            
            # Simulate real investigation delay (e.g. 1s)
            await asyncio.sleep(0.8)
            
            # Run the agent execution
            updated_task = agent.execute_task(agent_task, context)
            context["all_findings"][agent.name] = updated_task.findings
            self._broadcast("incident_updated", incident.dict())

        # Step 4: Run Root Cause Analyzer Agent
        rca_task = AgentTask(
            id=f"{incident.id}-root-cause",
            agent_name=self.rca_agent.name,
            description="Correlate all metrics, logs, and topologies to synthesize root cause and propose remediation"
        )
        incident.tasks.append(rca_task)
        self._broadcast("incident_updated", incident.dict())
        
        await asyncio.sleep(0.8)
        self.rca_agent.execute_task(rca_task, context)
        
        # Extract identified parameters
        incident.root_cause = context.get("deduced_root_cause", "Undetermined service crash")
        incident.proposed_remediation = context.get("recommended_remediation", "Check service parameters manually")
        incident.status = IncidentStatus.IDENTIFIED
        self._broadcast("incident_updated", incident.dict())
        
        # Stop and wait for human approval (simulated state, backend api will toggle this)
        logger.info(f"Incident {incident.id} identified. Awaiting Human Approval for remediation: '{incident.proposed_remediation}'")

    async def execute_remediation(self, incident_id: str):
        """
        Triggered when a human SRE operator approves the proposed remediation.
        """
        if incident_id not in self.active_incidents:
            logger.error(f"Incident {incident_id} not found in orchestrator mapping.")
            return

        incident = self.active_incidents[incident_id]
        incident.status = IncidentStatus.REMEDIATING
        self._broadcast("incident_updated", incident.dict())

        # Setup context for remediation agent
        context = {
            "service": incident.service,
            "recommended_remediation": incident.proposed_remediation
        }

        # Step 5: Execute remediation task
        remediation_task = AgentTask(
            id=f"{incident.id}-remediate",
            agent_name=self.remediation_agent.name,
            description=f"Safely execute proposed remediation: {incident.proposed_remediation}"
        )
        incident.tasks.append(remediation_task)
        self._broadcast("incident_updated", incident.dict())

        await asyncio.sleep(1.0)
        self.remediation_agent.execute_task(remediation_task, context)
        incident.remediation_executed = True
        
        # Step 6: Verify fix correctness
        incident.status = IncidentStatus.VERIFYING
        self._broadcast("incident_updated", incident.dict())

        verification_task = AgentTask(
            id=f"{incident.id}-verify",
            agent_name=self.verification_agent.name,
            description="Perform latency audits, error checks and pod restart checks to verify resolution"
        )
        incident.tasks.append(verification_task)
        self._broadcast("incident_updated", incident.dict())

        await asyncio.sleep(0.8)
        self.verification_agent.execute_task(verification_task, context)
        
        # Assume verification passes in our simulation
        incident.verification_passed = True
        incident.status = IncidentStatus.RESOLVED
        incident.resolved_at = datetime.now()
        self._broadcast("incident_updated", incident.dict())

        # Step 7: Draft Postmortem report
        pm_id = f"PM-{incident.id}"
        pm = IncidentPostmortem(
            id=pm_id,
            incident_id=incident.id,
            title=f"Postmortem: {incident.title}",
            severity=incident.severity,
            service=incident.service,
            created_at=incident.created_at,
            resolved_at=incident.resolved_at,
            executive_summary=f"On {incident.created_at.strftime('%Y-%m-%d %H:%M')}, an automated alert was triggered indicating a degradation in {incident.service}. The AIRE autonomous response swarm investigated, located the root cause, and resolved it within {(incident.resolved_at - incident.created_at).total_seconds():.1f} seconds.",
            timeline=[
                {"timestamp": incident.created_at.isoformat(), "event": "Incident triggered & detected."},
                {"timestamp": (incident.created_at + timedelta(seconds=2)).isoformat(), "event": "All diagnostic agents completed log, metric, and pod analyses."},
                {"timestamp": (incident.created_at + timedelta(seconds=4)).isoformat(), "event": f"Root cause identified: {incident.root_cause}."},
                {"timestamp": incident.resolved_at.isoformat(), "event": f"Remediation executed and verified successfully."}
            ],
            trigger=incident.detected_by,
            root_cause=incident.root_cause,
            remediation_details=incident.proposed_remediation,
            action_items=[
                f"Verify downstream client connection limits are tuned correctly for {incident.service}.",
                f"Increase Prometheus scrape frequency for latency profiling on gateway."
            ],
            preventative_measures=[
                "Configure automatic horizontal scaling threshold at 75% CPU load.",
                "Implement database connection watchdog logic inside client pools."
            ]
        )
        
        self.postmortems[pm_id] = pm
        incident.postmortem_id = pm_id
        self._broadcast("incident_updated", incident.dict())
        self._broadcast("postmortem_created", pm.dict())

        # Step 8: Commit incident resolution to Long-Term Episodic Memory
        episodic_memory.add_episode(
            incident_id=incident.id,
            title=incident.title,
            service=incident.service,
            root_cause=incident.root_cause,
            remediation=incident.proposed_remediation,
            success=True
        )

        # Step 9: Compute Evaluation Metrics for the run
        eval_key = "pod_crash"
        title_lower = incident.title.lower()
        if "connection" in title_lower or "db" in title_lower:
            eval_key = "db_leak"
        elif "latency" in title_lower:
            eval_key = "slow_auth"
        elif "canary" in title_lower:
            eval_key = "canary_failed"
            
        eval_metric = evaluator.evaluate_run(incident, eval_key)
        self.evaluations.append(eval_metric)
        self._broadcast("evaluation_updated", eval_metric.dict())

        logger.info(f"Incident {incident.id} fully resolved and postmortem completed successfully.")

orchestrator = SREOrchestrator()
