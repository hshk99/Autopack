# Security Policy

## Reporting Security Issues

This is a personal/internal-use tool. If you discover a security vulnerability:

1. **Do not create a public GitHub issue**
2. Contact the repository owner directly via GitHub

## Security Posture

Autopack is designed for **personal/internal use** with multi-device access (laptop + desktop). Security practices are lightweight and appropriate for this use case:

### Active Security Measures

1. **Visibility Scans** (informational, non-blocking):
   - Weekly CVE vulnerability scans
   - CodeQL static analysis
   - Trivy filesystem and container scans
   - Results visible in GitHub Security tab

2. **Secrets Hygiene**:
   - Gitleaks secret scanning
   - No credentials in code
   - Sanitized logging

3. **External API Hygiene**:
   - Circuit breakers for external service calls
   - Rate limiting
   - Timeouts and retries
   - Graceful degradation

4. **Multi-Device Access Protection**:
   - API key authentication for non-local access
   - Rate limiting on authentication endpoints
   - Protected high-impact endpoints (approvals, admin, action execution)

5. **Workflow Safety**:
   - SHA-pinned GitHub Actions
   - Default-deny governance (explicit approval required)

### Archived Infrastructure

The SARIF baseline and diff-gate enforcement system has been archived to `archive/security-infrastructure/` to reduce CI complexity for private/internal use. See [Restoration Guide](archive/security-infrastructure/RESTORATION_GUIDE.md) if you need to restore it.

## Downstream Project Security

If you build projects with Autopack that will be published or monetized, you must implement your own security posture:

- **Threat Modeling**: Define threats specific to your deployment model
- **Secure Hosting**: HTTPS, firewalls, secrets management
- **Release Pipeline**: Security scanning and approval workflow
- **Runtime Monitoring**: Intrusion detection, anomaly detection
- **Incident Response**: Define procedures for security incidents

Autopack's internal security practices are **not** a substitute for downstream project security.

## Supported Versions

This is a development tool for personal/internal use. Only the latest version on `main` is supported.

| Version | Supported |
| ------- | --------- |
| main    | Yes       |
| Other   | No        |
