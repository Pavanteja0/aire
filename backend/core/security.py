import re
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from backend.core.config import settings
from backend.core.models import save_audit_log_to_db

logger = logging.getLogger("aire.security")

class Role(str, Enum):
    ADMIN = "admin"
    SRE_LEAD = "sre_lead"
    SRE_ENGINEER = "sre_engineer"
    VIEWER = "viewer"

class Action(str, Enum):
    READ_METRICS = "read_metrics"
    READ_LOGS = "read_logs"
    RUN_DIAGNOSTICS = "run_diagnostics"
    RUN_REMEDIATION = "run_remediation"
    APPROVE_FIX = "approve_fix"

# Define RBAC Permissions Matrix
PERMISSIONS_MATRIX: Dict[Role, List[Action]] = {
    Role.ADMIN: [Action.READ_METRICS, Action.READ_LOGS, Action.RUN_DIAGNOSTICS, Action.RUN_REMEDIATION, Action.APPROVE_FIX],
    Role.SRE_LEAD: [Action.READ_METRICS, Action.READ_LOGS, Action.RUN_DIAGNOSTICS, Action.RUN_REMEDIATION, Action.APPROVE_FIX],
    Role.SRE_ENGINEER: [Action.READ_METRICS, Action.READ_LOGS, Action.RUN_DIAGNOSTICS, Action.APPROVE_FIX], # Cannot run remediation directly without Lead approval
    Role.VIEWER: [Action.READ_METRICS, Action.READ_LOGS]
}

class SecurityManager:
    """
    Coordinates RBAC authorization, audit logs, secrets redaction,
    and prompt injection filters.
    """
    def __init__(self):
        self.audit_log: List[Dict[str, Any]] = []

    def log_audit(self, actor: str, action: str, target: str, status: str, details: str = ""):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "actor": actor,
            "action": action,
            "target": target,
            "status": status,
            "details": details
        }
        self.audit_log.append(log_entry)
        try:
            save_audit_log_to_db(actor, action, target, status, details)
        except Exception as e:
            logger.error(f"Failed to persist audit log: {e}")
        logger.info(f"AUDIT LOG: {actor} | {action} on {target} -> {status} ({details})")

    def authorize(self, actor: str, role: Role, action: Action, target: str) -> bool:
        """
        Validates RBAC permissions for a given SRE action.
        """
        allowed_actions = PERMISSIONS_MATRIX.get(role, [])
        if action in allowed_actions:
            self.log_audit(actor, action.value, target, "APPROVED")
            return True
        else:
            self.log_audit(actor, action.value, target, "DENIED", f"Role {role.value} lacks permission")
            return False

    def redact_secrets(self, text: str) -> str:
        """
        Scans strings (like logs or LLM returns) and redacts matching credential patterns.
        """
        redacted = text
        for pattern in settings.SECRET_REDACTION_PATTERNS:
            redacted = re.sub(pattern, "[REDACTED_CREDENTIAL]", redacted)
        return redacted

    def detect_prompt_injection(self, text: str) -> bool:
        """
        Detects prompt injection vectors (system overrides, token leaks).
        """
        injection_indicators = [
            r"(?i)ignore\s+(?:all\s+)?previous\s+instructions",
            r"(?i)system\s+override",
            r"(?i)bypass\s+restrictions",
            r"(?i)you\s+are\s+now\s+a\s+hacker",
            r"(?i)dump\s+configuration",
            r"(?i)reveal\s+your\s+system\s+prompt"
        ]
        
        for pattern in injection_indicators:
            if re.search(pattern, text):
                self.log_audit("system", "prompt_injection_check", "input_string", "FLAGGED", f"Matched injection pattern: {pattern}")
                return True
        return False

    def validate_tool_arguments(self, tool_name: str, args: Dict[str, Any]) -> bool:
        """
        Sandboxes tool parameters to prevent command execution or file traversals.
        """
        # Ensure namespace arguments only match lowercase alphanumeric characters
        if "namespace" in args and not re.match(r"^[a-z0-9\-]+$", str(args["namespace"])):
            self.log_audit("system", "sandbox_validation", tool_name, "REJECTED", "Invalid characters in namespace argument")
            return False
            
        # Ensure service queries only match standard service structures
        if "service" in args and args["service"] and not re.match(r"^[a-zA-Z0-9\-_]+$", str(args["service"])):
            self.log_audit("system", "sandbox_validation", tool_name, "REJECTED", "Invalid characters in service argument")
            return False
            
        return True

security_manager = SecurityManager()
