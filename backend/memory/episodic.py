import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aire.memory.episodic")

class EpisodicMemoryStore:
    """
    Long-term episodic memory store that indexes past incidents,
    root causes, and historical remediation logs.
    """
    def __init__(self):
        # Seed historical incidents as long-term SRE memory
        self.episodes: List[Dict[str, Any]] = [
            {
                "incident_id": "INC-HIST-01",
                "title": "Kubernetes Pod CrashLoopBackOff on payment-service",
                "service": "payment-service",
                "root_cause": "OutOfMemoryError: Java heap space due to high transactional volume.",
                "remediation": "Triggered rollout restart of payment-service pod to flush memory and connections.",
                "success": True,
                "timestamp": (datetime.now() - timedelta(days=30)).isoformat()
            },
            {
                "incident_id": "INC-HIST-02",
                "title": "Database Connection Exhaustion Warning on payment-db",
                "service": "payment-db",
                "root_cause": "HikariPool connection leak in payment-service due to nested try-catch blocks failing to close SQL transactions.",
                "remediation": "Executed rollout restart of payment-service to forcefully close connections, then deployed hotfix patch reverting connection leak commit.",
                "success": True,
                "timestamp": (datetime.now() - timedelta(days=15)).isoformat()
            },
            {
                "incident_id": "INC-HIST-03",
                "title": "API Gateway Request Latency Alert",
                "service": "api-gateway",
                "root_cause": "Auth-service CPU bottleneck during password hashing algorithms load.",
                "remediation": "Scaled auth-service replicas from 2 to 6, redistributing ingress crypto load.",
                "success": True,
                "timestamp": (datetime.now() - timedelta(days=10)).isoformat()
            },
            {
                "incident_id": "INC-HIST-04",
                "title": "Canary Deployment Error Rate Spike",
                "service": "notification-service",
                "root_cause": "Canary release v1.2.0 introduced a null pointer exception in template parser.",
                "remediation": "Reverted version to v1.1.9 immediately using deployment rollback tool.",
                "success": True,
                "timestamp": (datetime.now() - timedelta(days=5)).isoformat()
            }
        ]

    def add_episode(self, incident_id: str, title: str, service: str, root_cause: str, remediation: str, success: bool = True):
        episode = {
            "incident_id": incident_id,
            "title": title,
            "service": service,
            "root_cause": root_cause,
            "remediation": remediation,
            "success": success,
            "timestamp": datetime.now().isoformat()
        }
        self.episodes.append(episode)
        logger.info(f"Memory: Recorded new episodic trace for incident {incident_id}")

    def recall_similar_incidents(self, title: str, service: str) -> List[Dict[str, Any]]:
        """
        Retrieves matching past incidents based on simple term overlap (service + keywords).
        """
        logger.info(f"Memory Recall: Searching past episodes for title='{title}', service='{service}'")
        
        matches = []
        q_words = set(title.lower().split())
        
        for ep in self.episodes:
            score = 0.0
            # Exact service match gives high weight
            if ep["service"] == service:
                score += 0.5
                
            # Count word matches
            ep_words = set(ep["title"].lower().split())
            overlap = q_words.intersection(ep_words)
            score += 0.1 * len(overlap)
            
            if score >= 0.2:
                matches.append((ep, score))
                
        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return [item[0] for item in matches]

episodic_memory = EpisodicMemoryStore()
