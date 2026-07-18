import math
import re
from typing import Dict, List, Set, Tuple

class DependencyGraph:
    """
    Graph representation of the architecture topology for Graph RAG routing.
    Tracks services, databases, and dependencies.
    """
    def __init__(self):
        self.nodes = {
            "api-gateway": {"type": "service", "desc": "Handles ingress requests and routes to auth/payments"},
            "auth-service": {"type": "service", "desc": "Decrypts tokens and authorizes user sessions"},
            "payment-service": {"type": "service", "desc": "Orchestrates payment transaction queries"},
            "payment-db": {"type": "database", "desc": "PostgreSQL database storing customer cards & audit ledger"},
            "notification-service": {"type": "service", "desc": "Dispatches email and SMS alerts via third-party APIs"}
        }
        self.edges = [
            ("api-gateway", "auth-service"),
            ("api-gateway", "payment-service"),
            ("payment-service", "payment-db"),
            ("payment-service", "notification-service"),
        ]

    def get_downstream(self, node: str) -> List[str]:
        return [target for source, target in self.edges if source == node]

    def get_upstream(self, node: str) -> List[str]:
        return [source for source, target in self.edges if target == node]

    def get_neighbors(self, node: str) -> Dict[str, List[str]]:
        return {
            "upstream": self.get_upstream(node),
            "downstream": self.get_downstream(node)
        }

class HybridRAGStore:
    """
    Implements a Hybrid Search (BM25 + Semantic Cosine Similarity) database
    to lookup runbooks, architecture docs, and operations wikis.
    """
    def __init__(self):
        self.documents = [
            {
                "id": "RUN-K8S-01",
                "title": "Kubernetes Out Of Memory (OOM) Crash Recovery Runbook",
                "content": "Symptom: Pod status is CrashLoopBackOff and terminates with exit code 137 (OOMKilled). Action: Check pod restart count. Check container limits. Inspect logs for heap errors. Remediation: Run rollout restart of the associated deployment to recycle dead connections or scale up memory limits if persistent.",
                "tags": ["kubernetes", "crashloop", "oomkilled", "restart"]
            },
            {
                "id": "RUN-DB-02",
                "title": "PostgreSQL Connection Leak and Pool Exhaustion Runbook",
                "content": "Symptom: Database errors showing 'remaining connection slots are reserved' or timeout in HikariPool connection request. Action: Verify active connection count on target DB. Inspect service logs for unclosed database connections. Remediation: Restart client service pods to force closing leaked connections, then commit a patch fixing connection leak.",
                "tags": ["database", "postgres", "pool", "exhaustion", "restart"]
            },
            {
                "id": "RUN-LATENCY-03",
                "title": "Microservice CPU Bottleneck & Latency Remediation Guide",
                "content": "Symptom: Average response latency spikes, CPU usage is near 100% on auth-service or crypto operations. Action: Correlate downstream service latencies. Check CPU throttling metrics. Remediation: Automatically scale replica set, route traffic away, or rollback latest canary version if the CPU spike corresponds to a recent version release.",
                "tags": ["latency", "cpu", "throttling", "canary", "rollback"]
            },
            {
                "id": "RUN-DEPLOY-04",
                "title": "CI/CD Canary Deployment Failure Rollback Runbook",
                "content": "Symptom: Elevated HTTP 5xx errors immediately following a deployment of notification-service or payment-service. Action: Query git deployments info. Check CI/CD status. Remediation: Perform instant deployment rollback to the previous stable release version on Git/ArgoCD.",
                "tags": ["deployment", "canary", "rollback", "http-500", "cicd"]
            }
        ]
        self.graph = DependencyGraph()

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\w+", text.lower())

    def _compute_tf_idf(self, query: str, doc_content: str) -> float:
        """Simple TF-IDF scoring simulation as a proxy for BM25 keyword matching"""
        q_tokens = self._tokenize(query)
        d_tokens = self._tokenize(doc_content)
        if not q_tokens or not d_tokens:
            return 0.0
            
        score = 0.0
        for token in q_tokens:
            # Term Frequency in Doc
            tf = d_tokens.count(token) / len(d_tokens)
            # Inverse Document Frequency
            doc_count = sum(1 for d in self.documents if token in self._tokenize(d["content"]))
            idf = math.log((1 + len(self.documents)) / (1 + doc_count)) + 1
            score += tf * idf
        return score

    def _compute_mock_semantic_similarity(self, query: str, doc_content: str) -> float:
        """
        Simulates semantic embedding cosine similarity.
        Matches overlapping conceptual keywords (e.g. latency -> slow, crash -> restart).
        """
        concept_synonyms = {
            "crash": {"crash", "crashloop", "oomkilled", "restarting", "exit", "oom"},
            "slow": {"slow", "latency", "bottleneck", "spike", "throttling", "timeout"},
            "db": {"db", "database", "postgres", "connection", "leak", "pool"},
            "deploy": {"deploy", "deployment", "canary", "version", "cicd", "rollback"}
        }
        
        q_tokens = set(self._tokenize(query))
        d_tokens = set(self._tokenize(doc_content))
        
        score = 0.0
        # Check concept overlaps
        for concept, words in concept_synonyms.items():
            q_has_concept = any(w in q_tokens for w in words)
            d_has_concept = any(w in d_tokens for w in words)
            if q_has_concept and d_has_concept:
                score += 0.4
                
        # Jaccard index baseline
        intersection = q_tokens.intersection(d_tokens)
        union = q_tokens.union(d_tokens)
        if union:
            score += 0.2 * (len(intersection) / len(union))
            
        return min(score, 1.0)

    def search(self, query: str, limit: int = 2) -> List[Dict[str, Any]]:
        """
        Performs hybrid retrieval: BM25/TF-IDF score + semantic similarity score.
        """
        results = []
        for doc in self.documents:
            tf_idf = self._compute_tf_idf(query, doc["content"])
            semantic = self._compute_mock_semantic_similarity(query, doc["content"])
            # Hybrid formula: 40% TF-IDF keyword match + 60% semantic match
            hybrid_score = (0.4 * tf_idf) + (0.6 * semantic)
            
            results.append({
                "doc": doc,
                "score": hybrid_score
            })
            
        # Sort descending by score
        results.sort(key=lambda x: x["score"], reverse=True)
        return [r["doc"] for r in results[:limit] if r["score"] > 0.05]

    def get_topology_context(self, service: str) -> Dict[str, Any]:
        """
        Returns architectural dependency mapping (Graph RAG helper).
        """
        neighbors = self.graph.get_neighbors(service)
        description = self.graph.nodes.get(service, {}).get("desc", "")
        return {
            "service": service,
            "description": description,
            "upstream_dependencies": neighbors["upstream"],
            "downstream_dependencies": neighbors["downstream"]
        }

rag_store = HybridRAGStore()
