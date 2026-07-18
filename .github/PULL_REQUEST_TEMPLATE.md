## 🚀 Pull Request Specification

### 📝 Summary of Changes
Provide a brief summary of the modifications, architectural implications, and user-facing benefits.

### 🏛️ Engineering Decisions (ADR Link)
* Has this change introduced a new architectural pattern? [Yes/No]
* Link to the updated/new ADR (if applicable):

### 🛡️ Security Checklists
- [ ] Input parameters validated/sanitized to prevent Prompt Injections.
- [ ] Secrets/Credentials verified as redacted from debug log lines.
- [ ] Database queries verified as scoped/idempotent to prevent locking faults.

### 🧪 Verification & Pytest Results
- [ ] E2E Pytest logs attached or verified green:
```bash
python -m pytest backend/tests/test_sre.py
```
- [ ] UI telemetry tested manually.
