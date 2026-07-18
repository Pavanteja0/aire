# AIRE Control Plane: Security & Threat Modeling

This document specifies the security boundary controls, Role-Based Access Control (RBAC) matrix, credential redaction filters, and prompt injection filters on the AIRE platform.

---

## 1. Role-Based Access Control (RBAC) Matrix

AIRE implements strict RBAC to prevent unauthorized actors from triggering raw container mutations or rolling back services.

| Role | Read Metrics | Read Logs | Run Diagnostics | Run Remediation | Approve Fix |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Admin** | Yes | Yes | Yes | Yes | Yes |
| **SRE Lead** | Yes | Yes | Yes | Yes | Yes |
| **SRE Engineer** | Yes | Yes | Yes | No | Yes |
| **Viewer** | Yes | Yes | No | No | No |

* **Remediation Guardrail**: SRE Engineers can execute diagnostic queries but cannot run production remediations (like rollout restarts) without explicit Lead/Admin approval.

---

## 2. Secrets Redaction & Logs Scrubbing

To prevent leaking sensitive API credentials, database passwords, or tokens in logs or LLM payloads, AIRE implements a regex-based **Secrets Redaction Filter** (`backend/core/security.py`):

```python
SECRET_REDACTION_PATTERNS = [
    r"(?i)password\s*=\s*['\"]([^'\"]+)['\"]",
    r"(?i)api[-_]key\s*=\s*['\"]?([a-zA-Z0-9]{16,})['\"]?",
    r"(?i)token\s*=\s*['\"]?([a-zA-Z0-9]{20,})['\"]?"
]
```

* Any matching string segment is automatically scrubbed and replaced with `[REDACTED_CREDENTIAL]` prior to display in UI panels or storage in the SQLite database.

---

## 3. Prompt Injection Protection

Malicious payloads could attempt to hijack the LLM swarm by placing system commands inside incident input parameters.

* **Heuristics Defenses**: An active injection analyzer checks inputs for bypass phrases (e.g. `ignore previous instructions`, `dump configurations`). If detected, the API immediately throws an `HTTP 400 Bad Request` and writes a security threat event.
* **Persistent Audit Logs**: All authorization approvals, blocks, and manual triggers write records directly to the persistent SQLite `audit_logs` table for compliance audits.
