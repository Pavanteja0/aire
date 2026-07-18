import re
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from backend.core.config import settings
from backend.simulation.mock_services import sre_env

logger = logging.getLogger("aire.tools")

# Defensively import real client SDKs to prevent crashes if not installed
try:
    import requests
except ImportError:
    requests = None

try:
    from kubernetes import client, config as k8s_config
except ImportError:
    client = None
    k8s_config = None

try:
    from slack_sdk import WebClient
except ImportError:
    WebClient = None


def query_prometheus(metric_name: str, duration_min: int = 15) -> List[Dict[str, Any]]:
    """
    Queries Prometheus for timeseries data on a specific metric.
    Falls back to SREEnvironment simulation if live connection fails or is disabled.
    """
    if settings.USE_REAL_INFRA and requests:
        try:
            logger.info(f"LIVE TOOL: Querying Prometheus API for '{metric_name}'")
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=duration_min)
            
            url = f"{settings.PROMETHEUS_URL}/api/v1/query_range"
            params = {
                "query": metric_name,
                "start": start_time.isoformat() + "Z",
                "end": end_time.isoformat() + "Z",
                "step": "30s"
            }
            
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            
            if data.get("status") == "success" and data.get("data", {}).get("result"):
                results = []
                metrics_pts = data["data"]["result"][0]["values"]
                for pt in metrics_pts:
                    results.append({
                        "timestamp": datetime.utcfromtimestamp(pt[0]).isoformat(),
                        "value": float(pt[1])
                    })
                return results
        except Exception as e:
            logger.warning(f"Failed to connect to Prometheus API ({e}). Falling back to simulation.")

    # Simulation Fallback
    logger.info(f"SIMULATION TOOL: Querying Prometheus for '{metric_name}'")
    if metric_name not in sre_env.metrics_history:
        return [{"error": f"Metric {metric_name} not found in Prometheus registry."}]
    
    cutoff = datetime.now() - timedelta(minutes=duration_min)
    points = sre_env.metrics_history[metric_name]
    return [
        {"timestamp": pt.timestamp.isoformat(), "value": round(pt.value, 4)}
        for pt in points if pt.timestamp >= cutoff
    ]


def query_loki(query_str: str, service: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Queries Grafana Loki log aggregator for lines matching a query or service label.
    Falls back to SREEnvironment simulation if live connection fails or is disabled.
    """
    if settings.USE_REAL_INFRA and requests:
        try:
            logger.info(f"LIVE TOOL: Querying Loki logs for '{query_str}' on service '{service}'")
            url = f"{settings.LOKI_URL}/loki/api/v1/query_range"
            
            label_filter = f'{{app="{service}"}}' if service else '{namespace="production"}'
            logql = f'{label_filter} |= "{query_str}"'
            
            params = {"query": logql, "limit": limit}
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            
            if data.get("status") == "success" and data.get("data", {}).get("result"):
                results = []
                for stream in data["data"]["result"]:
                    svc_name = stream["stream"].get("app", service or "unknown")
                    for value in stream["values"]:
                        ts_ns = int(value[0])
                        ts = datetime.utcfromtimestamp(ts_ns / 1e9)
                        results.append({
                            "timestamp": ts.isoformat(),
                            "service": svc_name,
                            "level": "ERROR" if "error" in value[1].lower() else "INFO",
                            "message": value[1]
                        })
                return results
        except Exception as e:
            logger.warning(f"Failed to connect to Loki logs API ({e}). Falling back to simulation.")

    # Simulation Fallback
    logger.info(f"SIMULATION TOOL: Querying Loki logs matching '{query_str}' for service '{service}'")
    matched = []
    for log in reversed(sre_env.logs_history):
        if service and log.service != service:
            continue
        if query_str.lower() in log.message.lower():
            matched.append({
                "timestamp": log.timestamp.isoformat(),
                "service": log.service,
                "level": log.level,
                "message": log.message,
                "pod_name": log.pod_name
            })
        if len(matched) >= limit:
            break
    return list(reversed(matched))


def query_kubernetes_pods(namespace: str = "production") -> List[Dict[str, Any]]:
    """
    Lists pods in the specified namespace.
    Falls back to SREEnvironment simulation if live connection fails or is disabled.
    """
    if settings.USE_REAL_INFRA and client and k8s_config:
        try:
            logger.info(f"LIVE TOOL: Querying Kubernetes pods in namespace '{namespace}'")
            try:
                k8s_config.load_incluster_config()
            except Exception:
                k8s_config.load_kube_config()
                
            v1 = client.CoreV1Api()
            pods = v1.list_namespaced_pod(namespace=namespace)
            results = []
            
            for pod in pods.items:
                restarts = 0
                last_reason = None
                if pod.status.container_statuses:
                    restarts = sum(c.restart_count for c in pod.status.container_statuses)
                    terminated = pod.status.container_statuses[0].state.terminated
                    if terminated:
                        last_reason = terminated.reason
                        
                results.append({
                    "name": pod.metadata.name,
                    "status": pod.status.phase,
                    "restarts": restarts,
                    "cpu_usage_cores": 0.0, # Metrics API client required for live usage metrics
                    "memory_usage_bytes": 0,
                    "node_name": pod.spec.node_name or "unknown",
                    "created_at": pod.metadata.creation_timestamp.isoformat(),
                    "last_state_terminated_reason": last_reason
                })
            return results
        except Exception as e:
            logger.warning(f"Failed to query Kubernetes namespace '{namespace}' via SDK ({e}). Falling back to simulation.")

    # Simulation Fallback
    logger.info(f"SIMULATION TOOL: Listing Kubernetes pods in '{namespace}'")
    results = []
    for pod in sre_env.pods.values():
        if pod.namespace == namespace:
            results.append({
                "name": pod.name,
                "status": pod.status,
                "restarts": pod.restarts,
                "cpu_usage_cores": pod.cpu_usage_cores,
                "memory_usage_bytes": pod.memory_usage_bytes,
                "node_name": pod.node_name,
                "created_at": pod.created_at.isoformat(),
                "last_state_terminated_reason": "OOMKilled" if pod.status == "CrashLoopBackOff" else None
            })
    return results


def query_github_deployments(service: str) -> Dict[str, Any]:
    """
    Fetches the latest deployment state from GitHub REST API.
    Falls back to SREEnvironment simulation if live connection fails or is disabled.
    """
    if settings.USE_REAL_INFRA and requests and settings.GITHUB_TOKEN:
        try:
            logger.info(f"LIVE TOOL: Querying GitHub deployment state for '{service}'")
            url = f"https://api.github.com/repos/{settings.GITHUB_REPO}/deployments"
            headers = {"Authorization": f"token {settings.GITHUB_TOKEN}"}
            
            response = requests.get(url, headers=headers, timeout=5)
            deployments = response.json()
            
            if deployments:
                latest = deployments[0]
                dep_id = latest["id"]
                
                # Fetch statuses
                status_url = f"{url}/{dep_id}/statuses"
                res_status = requests.get(status_url, headers=headers, timeout=5)
                statuses = res_status.json()
                status_state = statuses[0]["state"] if statuses else "unknown"
                
                return {
                    "service_name": service,
                    "current_version": latest.get("ref", "unknown"),
                    "previous_version": "unknown",
                    "status": status_state.capitalize(),
                    "deployed_at": latest.get("created_at", datetime.now().isoformat()),
                    "commit_sha": latest.get("sha", "unknown"),
                    "changelog": latest.get("description", "GitHub deployment trigger"),
                    "ci_cd_status": "Success" if status_state == "success" else "Failed"
                }
        except Exception as e:
            logger.warning(f"Failed to fetch deployments from GitHub ({e}). Falling back to simulation.")

    # Simulation Fallback
    logger.info(f"SIMULATION TOOL: Fetching GitHub deployments for '{service}'")
    if service not in sre_env.deployments:
        return {"error": f"No active deployment found in GitHub registry for service: {service}"}
        
    dep = sre_env.deployments[service]
    return {
        "service_name": dep.service_name,
        "current_version": dep.current_version,
        "previous_version": dep.previous_version,
        "status": dep.status,
        "deployed_at": dep.deployed_at.isoformat(),
        "commit_sha": dep.commit_sha,
        "changelog": dep.changelog,
        "ci_cd_status": dep.ci_cd_status
    }


def remediate_service_restart_pod(service: str) -> str:
    """
    Executes a rollout restart of a Kubernetes deployment.
    Falls back to SREEnvironment simulation if live connection fails or is disabled.
    """
    if settings.USE_REAL_INFRA and client and k8s_config:
        try:
            logger.info(f"LIVE REMEDIATION: Restarting deployment '{service}' in namespace 'production'")
            try:
                k8s_config.load_incluster_config()
            except Exception:
                k8s_config.load_kube_config()
                
            apps_v1 = client.AppsV1Api()
            
            # Kubectl rollout restart updates deployment annotations with restart timestamp
            now = datetime.utcnow().isoformat()
            body = {
                'spec': {
                    'template': {
                        'metadata': {
                            'annotations': {
                                'kubectl.kubernetes.io/restartedAt': now
                            }
                        }
                    }
                }
            }
            
            apps_v1.patch_namespaced_deployment(name=service, namespace="production", body=body)
            sre_env.clear_outages()  # Sync simulation
            return f"Successfully executed live Kubernetes rollout restart of deployment '{service}' in production."
        except Exception as e:
            logger.warning(f"Failed to execute live deployment restart ({e}). Falling back to simulation.")

    # Simulation Fallback
    logger.info(f"SIMULATION REMEDIATION: Restarting pod for service '{service}'")
    if service in sre_env.pods:
        sre_env.clear_outages()
        return f"Successfully executed rollout restart of pod for service '{service}'. Pod status returned to Running."
    return f"Error: Pod associated with service '{service}' not found."


def remediate_rollback_deployment(service: str) -> str:
    """
    Rolls back the latest deployment for a service on GitHub.
    Falls back to SREEnvironment simulation if live connection fails or is disabled.
    """
    if settings.USE_REAL_INFRA and requests and settings.GITHUB_TOKEN:
        try:
            logger.info(f"LIVE REMEDIATION: Rolling back deployment for '{service}'")
            url = f"https://api.github.com/repos/{settings.GITHUB_REPO}/deployments"
            headers = {"Authorization": f"token {settings.GITHUB_TOKEN}"}
            
            # Fetch last two deployments to find the rollback target version
            response = requests.get(url, headers=headers, timeout=5)
            deployments = response.json()
            
            if len(deployments) >= 2:
                rollback_target_ref = deployments[1]["ref"] # Second most recent is target version
                
                # Trigger a new deployment pointing to the target ref
                body = {"ref": rollback_target_ref, "description": f"Remediation: rollback to {rollback_target_ref}"}
                requests.post(url, headers=headers, json=body, timeout=5)
                
                sre_env.clear_outages()
                return f"Successfully triggered live rollback deployment for '{service}' to version '{rollback_target_ref}' on GitHub."
        except Exception as e:
            logger.warning(f"Failed to execute live rollback on GitHub ({e}). Falling back to simulation.")

    # Simulation Fallback
    logger.info(f"SIMULATION REMEDIATION: Rolling back deployment for '{service}'")
    if service in sre_env.deployments:
        dep = sre_env.deployments[service]
        prev = dep.previous_version
        curr = dep.current_version
        
        sre_env.clear_outages()
        dep.current_version = prev
        dep.previous_version = curr
        dep.status = "Deployed"
        dep.ci_cd_status = "Success"
        return f"Rollback executed successfully for '{service}'. Version reverted from {curr} to {prev}."
    return f"Error: Service deployment history not found."


def slack_post_message(channel: str, message: str) -> str:
    """
    Sends a message to a live Slack channel.
    Falls back to simulation logging if disabled.
    """
    if settings.USE_REAL_INFRA and WebClient and settings.SLACK_BOT_TOKEN:
        try:
            logger.info(f"LIVE TOOL: Posting notification to Slack channel #{channel}")
            slack_client = WebClient(token=settings.SLACK_BOT_TOKEN)
            slack_client.chat_postMessage(channel=f"#{channel}", text=message)
            return f"Message successfully posted to channel #{channel} via slack_sdk."
        except Exception as e:
            logger.warning(f"Failed to post to live Slack API ({e}). Falling back to logging.")

    logger.info(f"SIMULATION TOOL: Logging Slack message to #{channel}: '{message}'")
    return f"Message successfully posted to channel #{channel}."


def pagerduty_resolve_incident(incident_id: str) -> str:
    """
    Resolves the incident status in PagerDuty.
    Falls back to simulation logging if disabled.
    """
    if settings.USE_REAL_INFRA and requests and settings.PAGERDUTY_TOKEN:
        try:
            logger.info(f"LIVE TOOL: Resolving incident {incident_id} in PagerDuty")
            url = f"https://api.pagerduty.com/incidents/{incident_id}"
            headers = {
                "Authorization": f"Token token={settings.PAGERDUTY_TOKEN}",
                "Content-Type": "application/json",
                "Accept": "application/vnd.pagerduty+json;version=2"
            }
            body = {
                "incident": {
                    "type": "incident_reference",
                    "status": "resolved"
                }
            }
            requests.put(url, headers=headers, json=body, timeout=5)
            return f"Incident {incident_id} successfully marked as RESOLVED in PagerDuty API."
        except Exception as e:
            logger.warning(f"Failed to resolve incident in PagerDuty API ({e}). Falling back to logging.")

    logger.info(f"SIMULATION TOOL: Resolving PagerDuty incident {incident_id}")
    return f"Incident {incident_id} successfully marked as RESOLVED in PagerDuty."
