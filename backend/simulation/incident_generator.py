import asyncio
import logging
from datetime import datetime
from typing import List, Optional
from backend.core.config import settings
from backend.core.models import Incident, IncidentSeverity, IncidentStatus
from backend.simulation.mock_services import sre_env

logger = logging.getLogger("aire.simulation")

class IncidentGenerator:
    """
    Scans the SREEnvironment and raises high-level SRE alerts / incidents.
    Also provides utility functions to trigger synthetic outages.
    """
    
    def check_thresholds(self) -> List[Incident]:
        """
        Analyses current metrics and container statuses, and generates
        Incident alerts if threshold parameters are violated.
        """
        incidents = []
        
        # 1. Check Pod crashes
        for name, pod in sre_env.pods.items():
            if pod.status == "CrashLoopBackOff":
                incidents.append(Incident(
                    id=f"INC-K8S-{name.upper()}-{int(datetime.now().timestamp())}",
                    title=f"Kubernetes Pod CrashLoopBackOff on {name}",
                    description=f"Pod {pod.name} in namespace {pod.namespace} is in status CrashLoopBackOff with {pod.restarts} restarts. Last termination state: OOMKilled.",
                    severity=IncidentSeverity.SEV1,
                    status=IncidentStatus.DETECTED,
                    service=name,
                    detected_by="KubernetesLivenessProbe"
                ))

        # 2. Check Latency Spikes
        latencies = sre_env.metrics_history["api-gateway_latency"]
        if latencies and latencies[-1].value > settings.LATENCY_THRESHOLD_MS:
            val = latencies[-1].value
            incidents.append(Incident(
                id=f"INC-LATENCY-GW-{int(datetime.now().timestamp())}",
                title="API Gateway Request Latency Alert",
                description=f"Average response latency on API Gateway has breached the threshold of {settings.LATENCY_THRESHOLD_MS}ms. Current value: {val:.2f}ms.",
                severity=IncidentSeverity.SEV2,
                status=IncidentStatus.DETECTED,
                service="api-gateway",
                detected_by="PrometheusAlertManager"
            ))

        # 3. Check Database Connections Leak
        conns = sre_env.metrics_history["payment-db_connections"]
        if conns and conns[-1].value >= 90:
            val = conns[-1].value
            incidents.append(Incident(
                id=f"INC-DB-CONN-{int(datetime.now().timestamp())}",
                title="Database Connection Exhaustion Warning",
                description=f"Active connection pool utilization on payment-db is dangerously high. Current active connections: {val}/100.",
                severity=IncidentSeverity.SEV1,
                status=IncidentStatus.DETECTED,
                service="payment-db",
                detected_by="PrometheusAlertManager"
            ))

        # 4. Check Deployment Failures / Canary Errors
        notif_errs = sre_env.metrics_history["notification-service_error_rate"]
        if notif_errs and notif_errs[-1].value > settings.ERROR_RATE_THRESHOLD_PCT:
            val = notif_errs[-1].value
            incidents.append(Incident(
                id=f"INC-DEPLOY-ERR-{int(datetime.now().timestamp())}",
                title="Canary Deployment Error Rate Spike",
                description=f"Error rate on notification-service has spiked following version deployment. Current value: {val:.2f}%.",
                severity=IncidentSeverity.SEV2,
                status=IncidentStatus.DETECTED,
                service="notification-service",
                detected_by="PrometheusAlertManager"
            ))

        return incidents

    def trigger_incident(self, incident_type: str) -> Optional[Incident]:
        """
        Injects a synthetic incident in the simulated environment.
        """
        logger.info(f"Injecting outage: {incident_type}")
        if incident_type == "pod_crash":
            sre_env.inject_outage("POD_CRASH_LOOP")
        elif incident_type == "db_leak":
            sre_env.inject_outage("DB_CONNECTION_LEAK")
        elif incident_type == "slow_auth":
            sre_env.inject_outage("API_LATENCY_SPIKE")
        elif incident_type == "canary_failed":
            sre_env.inject_outage("FAILED_CANARY_DEPLOYMENT")
        else:
            return None
        
        # Check thresholds immediately to return the generated incident
        incidents = self.check_thresholds()
        return incidents[0] if incidents else None

incident_generator = IncidentGenerator()
