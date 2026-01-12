"""API routes package.

Domain routers extracted from main.py (PR-API-3+).

Current routers:
- health.py: Health check and root endpoints
- files.py: File upload operations
- storage.py: Storage optimization endpoints (scan, cleanup, steam, recommendations)
- dashboard.py: Dashboard metrics and status endpoints (usage, models, token-efficiency)
- governance.py: Governance approval endpoints (pending requests, approve/deny)
- approvals.py: Approval requests and Telegram webhook handlers
- artifacts.py: Artifact browsing endpoints (index, file content, browser artifacts)
- phases.py: Phase status and result endpoints (update, record_issue, builder/auditor results)
- runs.py: Run management endpoints (start, get, list, progress, issues, errors)
"""
