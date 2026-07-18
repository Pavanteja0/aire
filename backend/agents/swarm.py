import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from backend.core.models import AgentTask, AgentTaskStatus
from backend.agents import tools

logger = logging.getLogger("aire.agents.swarm")

class BaseSREAgent:
    """Base SRE Agent containing reasoning telemetry and task runner interface."""
    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role

    def execute_task(self, task: AgentTask, context: Dict[str, Any]) -> AgentTask:
        raise NotImplementedError

class LogInvestigator(BaseSREAgent):
    """Queries log aggregation systems (Loki) to extract error signatures and stack traces."""
    def __init__(self):
        super().__init__(name="LogInvestigator", role="Log & Stacktrace Correlation")

    def execute_task(self, task: AgentTask, context: Dict[str, Any]) -> AgentTask:
        task.status = AgentTaskStatus.RUNNING
        service = context.get("service", "")
        
        # Tool Call: query logs
        tool_call = {
            "tool": "query_loki",
            "args": {"query_str": "error", "service": service}
        }
        task.tool_calls.append(tool_call)
        
        # Run tool
        logs = tools.query_loki(query_str="error", service=service, limit=5)
        fatal_logs = tools.query_loki(query_str="fatal", service=service, limit=5)
        all_logs = logs + fatal_logs
        
        # Analyze results
        findings = []
        if all_logs:
            findings.append(f"Detected {len(all_logs)} critical log entries matching error/fatal signatures:")
            for log in all_logs[:3]:
                findings.append(f"  - [{log['timestamp']}] [{log['level']}] {log['message']}")
        else:
            findings.append("No explicit error/fatal log messages found in Loki history.")
            
        task.findings = "\n".join(findings)
        task.status = AgentTaskStatus.SUCCESS
        task.completed_at = datetime.now()
        return task

class MetricsInvestigator(BaseSREAgent):
    """Analyzes timeseries charts (Prometheus) to diagnose traffic anomalies and resource bottlenecks."""
    def __init__(self):
        super().__init__(name="MetricsInvestigator", role="TimeSeries Performance Profiler")

    def execute_task(self, task: AgentTask, context: Dict[str, Any]) -> AgentTask:
        task.status = AgentTaskStatus.RUNNING
        service = context.get("service", "")
        
        # Determine metrics to query based on service
        metrics_to_check = []
        if service == "payment-service":
            metrics_to_check = ["payment-service_latency", "payment-service_error_rate"]
        elif service == "payment-db":
            metrics_to_check = ["payment-db_connections", "payment-db_cpu"]
        elif service == "api-gateway":
            metrics_to_check = ["api-gateway_latency", "api-gateway_error_rate"]
        else:
            metrics_to_check = ["api-gateway_latency", "api-gateway_error_rate"]
            
        findings = []
        for metric in metrics_to_check:
            tool_call = {
                "tool": "query_prometheus",
                "args": {"metric_name": metric, "duration_min": 10}
            }
            task.tool_calls.append(tool_call)
            
            pts = tools.query_prometheus(metric, duration_min=10)
            if pts and "error" not in pts[0]:
                avg_val = sum(p["value"] for p in pts) / len(pts)
                max_val = max(p["value"] for p in pts)
                findings.append(f"Metric '{metric}': average={avg_val:.2f}, max={max_val:.2f} (sampled {len(pts)} points).")
            else:
                findings.append(f"Metric '{metric}': No metrics retrieved or metric unrecognized.")
                
        task.findings = "\n".join(findings)
        task.status = AgentTaskStatus.SUCCESS
        task.completed_at = datetime.now()
        return task

class KubernetesInspector(BaseSREAgent):
    """Queries K8s stateful configurations to spot crashloops, CPU throttling, or pending pods."""
    def __init__(self):
        super().__init__(name="KubernetesInspector", role="Container Workload Diagnostics")

    def execute_task(self, task: AgentTask, context: Dict[str, Any]) -> AgentTask:
        task.status = AgentTaskStatus.RUNNING
        
        tool_call = {
            "tool": "query_kubernetes_pods",
            "args": {"namespace": "production"}
        }
        task.tool_calls.append(tool_call)
        
        pods = tools.query_kubernetes_pods(namespace="production")
        findings = []
        crashed_pods = [p for p in pods if p["status"] != "Running"]
        
        findings.append(f"Inspected production namespace. Total pods: {len(pods)}.")
        if crashed_pods:
            for p in crashed_pods:
                findings.append(f"  - WARNING: Pod '{p['name']}' is in status '{p['status']}' with {p['restarts']} restarts. Last Terminated Reason: {p['last_state_terminated_reason']}.")
        else:
            findings.append("  - All pods report Running status, no restarts observed.")
            
        task.findings = "\n".join(findings)
        task.status = AgentTaskStatus.SUCCESS
        task.completed_at = datetime.now()
        return task

class RootCauseAnalyzer(BaseSREAgent):
    """Correlates logs, metrics, topologies (Graph RAG), and memory to identify the root failure reason."""
    def __init__(self):
        super().__init__(name="RootCauseAnalyzer", role="Postmortem & Failure Correlation")

    def execute_task(self, task: AgentTask, context: Dict[str, Any]) -> AgentTask:
        task.status = AgentTaskStatus.RUNNING
        service = context.get("service", "")
        
        # Gathers findings from other tasks in the context
        all_findings = context.get("all_findings", {})
        topology = context.get("topology", {})
        similar_incidents = context.get("similar_incidents", [])
        
        findings = []
        findings.append("## Root Cause Synthesis Analysis")
        findings.append(f"1. Core Service: {service}")
        findings.append(f"2. Topology Context: Downstream links: {topology.get('downstream_dependencies', [])}")
        
        # Logic to deduce root cause based on findings text
        findings_str = json.dumps(all_findings).lower()
        deduced_cause = "Unknown anomaly"
        remediation_action = "Restart service pods to recover baseline health."
        
        if "oomkilled" in findings_str or "outofmemory" in findings_str:
            deduced_cause = "Java heap space OutOfMemoryError causing container CrashLoopBackOff."
            remediation_action = "Rollout restart of service pods to flush memory, with subsequent recommendation to scale JVM container heap size limits."
        elif "connection slots are reserved" in findings_str or "hikaripool" in findings_str:
            deduced_cause = "HikariCP database connection pool leakage in client service, causing connection exhaustion on payment-db."
            remediation_action = "Restart client service pods to force close leaked connections, and schedule DB version rollback."
        elif "slow response" in findings_str or "throttling" in findings_str:
            deduced_cause = "Downstream service auth-service bottlenecking on high-load crypto hashing operations."
            remediation_action = "Scale replicas of auth-service deployment to balance cryptographic parsing load."
        elif "uncaught typeerror" in findings_str or "canary" in findings_str:
            deduced_cause = "Failed canary deployment of version v1.2.0, introducing a null template property error in production."
            remediation_action = "Rollback canary deployment to previous stable version v1.1.9."

        findings.append(f"\n**Identified Root Cause**: {deduced_cause}")
        findings.append(f"**Recommended Remediation**: {remediation_action}")
        
        if similar_incidents:
            findings.append(f"\n*Historical Reference*: Found {len(similar_incidents)} matching incident(s) in long-term memory. Recommending verified fix from INC {similar_incidents[0]['incident_id']}.")
            
        task.findings = "\n".join(findings)
        task.status = AgentTaskStatus.SUCCESS
        task.completed_at = datetime.now()
        
        # Save deduced properties in context for subsequent agents
        context["deduced_root_cause"] = deduced_cause
        context["recommended_remediation"] = remediation_action
        
        return task

class RemediationAgent(BaseSREAgent):
    """Executes safe recovery tasks (rollbacks, restarts, replica scaling) following approval validation."""
    def __init__(self):
        super().__init__(name="RemediationAgent", role="Remediation Driver")

    def execute_task(self, task: AgentTask, context: Dict[str, Any]) -> AgentTask:
        task.status = AgentTaskStatus.RUNNING
        service = context.get("service", "")
        remediation = context.get("recommended_remediation", "")
        
        action_result = ""
        # Match remediation action to actual tool trigger
        if "rollback" in remediation.lower():
            tool_call = {
                "tool": "remediate_rollback_deployment",
                "args": {"service": service}
            }
            task.tool_calls.append(tool_call)
            action_result = tools.remediate_rollback_deployment(service)
        else:
            # Default to service rollout restart
            tool_call = {
                "tool": "remediate_service_restart_pod",
                "args": {"service": service}
            }
            task.tool_calls.append(tool_call)
            action_result = tools.remediate_service_restart_pod(service)
            
        task.findings = f"Remediation Execution Result:\n{action_result}"
        task.status = AgentTaskStatus.SUCCESS
        task.completed_at = datetime.now()
        return task

class VerificationAgent(BaseSREAgent):
    """Performs regression testing and metric evaluation to verify target services have fully recovered."""
    def __init__(self):
        super().__init__(name="VerificationAgent", role="Recovery Auditor")

    def execute_task(self, task: AgentTask, context: Dict[str, Any]) -> AgentTask:
        task.status = AgentTaskStatus.RUNNING
        service = context.get("service", "")
        
        findings = []
        findings.append("## Verifying System Health Post-Fix")
        
        # Check pods status
        tool_call_1 = {
            "tool": "query_kubernetes_pods",
            "args": {"namespace": "production"}
        }
        task.tool_calls.append(tool_call_1)
        pods = tools.query_kubernetes_pods(namespace="production")
        unhealthy_pods = [p for p in pods if p["status"] != "Running" and p["namespace"] == "production"]
        
        if not unhealthy_pods:
            findings.append("- K8s Pod Audit: Passed. All pods in production report Running status.")
        else:
            findings.append(f"- K8s Pod Audit: Failed. {len(unhealthy_pods)} pods unhealthy.")
            
        # Check latency thresholds
        tool_call_2 = {
            "tool": "query_prometheus",
            "args": {"metric_name": "api-gateway_latency", "duration_min": 2}
        }
        task.tool_calls.append(tool_call_2)
        pts = tools.query_prometheus("api-gateway_latency", duration_min=2)
        
        if pts and "error" not in pts[0]:
            recent_latency = pts[-1]["value"]
            if recent_latency < 300.0:
                findings.append(f"- API Gateway Latency Audit: Passed. Latency is stable at {recent_latency:.2f}ms (threshold 300.0ms).")
            else:
                findings.append(f"- API Gateway Latency Audit: Failed. Current latency is {recent_latency:.2f}ms.")
        else:
            findings.append("- API Gateway Latency Audit: Skipped. Metrics unavailable.")
            
        task.findings = "\n".join(findings)
        task.status = AgentTaskStatus.SUCCESS
        task.completed_at = datetime.now()
        return task
