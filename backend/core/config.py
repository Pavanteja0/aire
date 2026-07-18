import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Base paths
    WORKSPACE_ROOT: Path = Path("C:/Users/KALYAN/.gemini/antigravity/scratch/aire")
    DB_PATH: Path = Path("C:/Users/KALYAN/.gemini/antigravity/scratch/aire/backend/aire.db")
    
    # Toggle to switch from local mock simulation to live APIs
    USE_REAL_INFRA: bool = False
    
    # Real Infrastructure Endpoints
    PROMETHEUS_URL: str = "http://prometheus-k8s.monitoring.svc.cluster.local:9090"
    LOKI_URL: str = "http://loki.monitoring.svc.cluster.local:3100"
    SLACK_BOT_TOKEN: str = ""
    GITHUB_TOKEN: str = ""
    GITHUB_REPO: str = "google/antigravity"
    PAGERDUTY_TOKEN: str = ""
    
    # SRE Simulation configuration
    SIMULATION_TICK_RATE_SEC: int = 5
    RETENTION_PERIOD_HOURS: int = 24
    
    # LLM Settings
    LLM_API_KEY: str = "mock-key-for-local-execution"
    MODEL_REASONING: str = "gemini-2.5-pro"
    MODEL_EMBEDDING: str = "text-embedding-004"
    
    # Security Configuration
    SECRET_REDACTION_PATTERNS: list[str] = [
        r"(?i)api[-_]?key\s*[:=]\s*['\"]?[a-zA-Z0-9_\-\.\/]+['\"]?",
        r"(?i)password\s*[:=]\s*['\"]?[a-zA-Z0-9_\-\.\/]+['\"]?",
        r"(?i)token\s*[:=]\s*['\"]?[a-zA-Z0-9_\-\.\/]+['\"]?",
        r"(?i)db_password\s*[:=]\s*['\"]?[a-zA-Z0-9_\-\.\/]+['\"]?",
        r"bearer\s+[a-zA-Z0-9_\-\.]+"
    ]
    
    # SRE Alerting thresholds
    LATENCY_THRESHOLD_MS: float = 300.0
    CPU_THRESHOLD_PCT: float = 85.0
    MEMORY_THRESHOLD_PCT: float = 90.0
    ERROR_RATE_THRESHOLD_PCT: float = 2.0
    
    model_config = SettingsConfigDict(
        env_prefix="AIRE_",
        case_sensitive=True
    )

settings = Settings()
# Ensure directories exist
settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
