import random
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from backend.core.models import KubernetesPod, LogEntry, MetricPoint, DeploymentInfo

class SREEnvironment:
    """
    Simulates a production environment with pods, logs, metrics, and deployments.
    Allows injecting outages and updates metrics/logs dynamically based on state.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        self.pods: Dict[str, KubernetesPod] = {
            "api-gateway": KubernetesPod(
                name="api-gateway-7f8d9b-abc12", namespace="production", status="Running",
                restarts=0, cpu_usage_cores=0.25, memory_usage_bytes=128 * 1024 * 1024,
                node_name="node-1", created_at=datetime.now() - timedelta(days=5)
            ),
            "payment-service": KubernetesPod(
                name="payment-service-5c6e8f-xyz34", namespace="production", status="Running",
                restarts=0, cpu_usage_cores=0.4, memory_usage_bytes=256 * 1024 * 1024,
                node_name="node-2", created_at=datetime.now() - timedelta(days=5)
            ),
            "payment-db": KubernetesPod(
                name="payment-db-0", namespace="production", status="Running",
                restarts=0, cpu_usage_cores=0.8, memory_usage_bytes=1024 * 1024 * 1024,
                node_name="node-3", created_at=datetime.now() - timedelta(days=10)
            ),
            "auth-service": KubernetesPod(
                name="auth-service-9a8b7c-def56", namespace="production", status="Running",
                restarts=0, cpu_usage_cores=0.15, memory_usage_bytes=96 * 1024 * 1024,
                node_name="node-1", created_at=datetime.now() - timedelta(days=5)
            ),
            "notification-service": KubernetesPod(
                name="notification-service-2e3d4f-ghi78", namespace="production", status="Running",
                restarts=0, cpu_usage_cores=0.1, memory_usage_bytes=80 * 1024 * 1024,
                node_name="node-2", created_at=datetime.now() - timedelta(days=2)
            ),
        }
        
        self.deployments: Dict[str, DeploymentInfo] = {
            "notification-service": DeploymentInfo(
                service_name="notification-service", current_version="v1.1.9", previous_version="v1.1.8",
                status="Deployed", deployed_at=datetime.now() - timedelta(days=2),
                commit_sha="a7b8c9d", changelog="Fix template rendering null pointer exception",
                ci_cd_status="Success"
            ),
            "payment-service": DeploymentInfo(
                service_name="payment-service", current_version="v2.0.4", previous_version="v2.0.3",
                status="Deployed", deployed_at=datetime.now() - timedelta(days=5),
                commit_sha="f3e2d1c", changelog="Optimize SQL query indices for payments table",
                ci_cd_status="Success"
            )
        }

        self.logs_history: List[LogEntry] = []
        self.metrics_history: Dict[str, List[MetricPoint]] = {
            "api-gateway_latency": [],
            "api-gateway_error_rate": [],
            "payment-service_latency": [],
            "payment-service_error_rate": [],
            "payment-db_connections": [],
            "payment-db_cpu": [],
            "auth-service_latency": [],
            "notification-service_error_rate": []
        }

        self.active_outages: Dict[str, Any] = {}
        self.tick_counter = 0

        # Seed initial 30 minutes of historical metrics to simulate clean charts
        self.seed_history()

    def seed_history(self):
        now = datetime.now()
        for i in range(60):  # 60 data points, 30s apart
            ts = now - timedelta(seconds=(60 - i) * 30)
            self._generate_data_point(ts)

    def _generate_data_point(self, timestamp: datetime):
        # Base healthy values
        latency_api = random.uniform(15, 25)
        err_api = random.uniform(0.01, 0.08)
        
        latency_pay = random.uniform(40, 60)
        err_pay = random.uniform(0.0, 0.05)
        
        db_conn = int(random.uniform(15, 25))
        db_cpu = random.uniform(10, 18)
        
        latency_auth = random.uniform(8, 12)
        err_notif = random.uniform(0.0, 0.1)

        # Apply active outages
        if "POD_CRASH_LOOP" in self.active_outages:
            # payment-service is crashing
            pod = self.pods["payment-service"]
            pod.status = "CrashLoopBackOff"
            if self.tick_counter % 3 == 0:
                pod.restarts += 1
            pod.cpu_usage_cores = 0.0
            pod.memory_usage_bytes = 0
            
            latency_api = random.uniform(800, 1500)
            err_api = random.uniform(45.0, 60.0)
            err_pay = 100.0
            latency_pay = 0.0
            
            # Inject crash logs
            self.logs_history.append(LogEntry(
                timestamp=timestamp, service="payment-service", level="ERROR",
                message="FATAL EXCEPTION: OutOfMemoryError: Java heap space",
                pod_name=pod.name
            ))
            self.logs_history.append(LogEntry(
                timestamp=timestamp, service="kubernetes", level="WARNING",
                message=f"Pod {pod.name} failed liveness probe, restarting",
                pod_name=pod.name
            ))

        if "DB_CONNECTION_LEAK" in self.active_outages:
            # payment-db connections leak
            db_conn = 100  # Max limit
            db_cpu = random.uniform(92, 99)
            latency_pay = random.uniform(2000, 4500)
            err_pay = random.uniform(10.0, 30.0)
            latency_api = random.uniform(500, 1200)
            err_api = random.uniform(5.0, 15.0)
            
            self.pods["payment-db"].cpu_usage_cores = 1.95
            self.pods["payment-db"].memory_usage_bytes = 980 * 1024 * 1024
            
            self.logs_history.append(LogEntry(
                timestamp=timestamp, service="payment-db", level="FATAL",
                message="FATAL: remaining connection slots are reserved for non-replication superuser connections",
                pod_name=self.pods["payment-db"].name
            ))
            self.logs_history.append(LogEntry(
                timestamp=timestamp, service="payment-service", level="ERROR",
                message="HikariPool-1 - Connection is not available, request timed out after 30000ms.",
                pod_name=self.pods["payment-service"].name
            ))

        if "API_LATENCY_SPIKE" in self.active_outages:
            # Downstream dependency auth-service slows down
            latency_auth = random.uniform(1200, 2200)
            latency_api = random.uniform(1300, 2400)
            err_api = random.uniform(2.0, 8.0)
            
            self.pods["auth-service"].cpu_usage_cores = 0.95  # Maxing CPU
            
            self.logs_history.append(LogEntry(
                timestamp=timestamp, service="auth-service", level="WARN",
                message="Slow response from crypto verify. CPU throttling active.",
                pod_name=self.pods["auth-service"].name
            ))
            self.logs_history.append(LogEntry(
                timestamp=timestamp, service="api-gateway", level="WARN",
                message="Upstream response slow from service 'auth-service' duration_ms=1850",
                pod_name=self.pods["api-gateway"].name
            ))

        if "FAILED_CANARY_DEPLOYMENT" in self.active_outages:
            # Canary deployment of notification-service version v1.2.0 fails
            err_notif = random.uniform(25.0, 40.0)
            dep = self.deployments["notification-service"]
            dep.current_version = "v1.2.0"
            dep.ci_cd_status = "Failed"
            dep.status = "Failed"
            dep.changelog = "Refactor email template sending layout engine"
            
            self.logs_history.append(LogEntry(
                timestamp=timestamp, service="notification-service", level="ERROR",
                message="Uncaught TypeError: Cannot read property 'template_id' of undefined at Mailer.send",
                pod_name=self.pods["notification-service"].name
            ))

        # Append metrics
        self.metrics_history["api-gateway_latency"].append(MetricPoint(timestamp=timestamp, value=latency_api))
        self.metrics_history["api-gateway_error_rate"].append(MetricPoint(timestamp=timestamp, value=err_api))
        self.metrics_history["payment-service_latency"].append(MetricPoint(timestamp=timestamp, value=latency_pay))
        self.metrics_history["payment-service_error_rate"].append(MetricPoint(timestamp=timestamp, value=err_pay))
        self.metrics_history["payment-db_connections"].append(MetricPoint(timestamp=timestamp, value=db_conn))
        self.metrics_history["payment-db_cpu"].append(MetricPoint(timestamp=timestamp, value=db_cpu))
        self.metrics_history["auth-service_latency"].append(MetricPoint(timestamp=timestamp, value=latency_auth))
        self.metrics_history["notification-service_error_rate"].append(MetricPoint(timestamp=timestamp, value=err_notif))

        # Routine background logs (heartbeats)
        if random.random() < 0.2 and not self.active_outages:
            self.logs_history.append(LogEntry(
                timestamp=timestamp, service="api-gateway", level="INFO",
                message=f"GET /api/v1/health - 200 OK - {random.uniform(1.2, 3.5):.2f}ms"
            ))

        # Truncate histories to avoid bloating memory
        max_history = 100
        for k in self.metrics_history:
            self.metrics_history[k] = self.metrics_history[k][-max_history:]
        self.logs_history = self.logs_history[-500:]

    def tick(self):
        """Ticks the simulation forward by 1 step (simulated time)"""
        self.tick_counter += 1
        now = datetime.now()
        self._generate_data_point(now)

    def inject_outage(self, outage_type: str):
        self.reset()
        self.active_outages[outage_type] = True
        # Speed-simulate outage starting logs
        for i in range(10):
            ts = datetime.now() - timedelta(seconds=(10 - i) * 10)
            self._generate_data_point(ts)

    def clear_outages(self):
        self.active_outages.clear()
        # Reset pods back to healthy
        for name, pod in self.pods.items():
            pod.status = "Running"
            pod.restarts = 0
            if name == "payment-service":
                pod.cpu_usage_cores = 0.4
                pod.memory_usage_bytes = 256 * 1024 * 1024
            elif name == "payment-db":
                pod.cpu_usage_cores = 0.8
                pod.memory_usage_bytes = 1024 * 1024 * 1024
            elif name == "auth-service":
                pod.cpu_usage_cores = 0.15
            elif name == "notification-service":
                pod.cpu_usage_cores = 0.1
                dep = self.deployments["notification-service"]
                dep.current_version = "v1.1.9"
                dep.ci_cd_status = "Success"
                dep.status = "Deployed"

        # Generate some clean data points
        for i in range(5):
            self.tick()

sre_env = SREEnvironment()
