# Security Policy

## Reporting Security Issues

This is a personal/internal-use tool. If you discover a security vulnerability:

1. **Do not create a public GitHub issue**
2. Contact the repository owner directly via GitHub

## Security Documentation

For detailed security documentation, see:

- [Security Baseline System](security/README.md) - Baseline + diff gate system
- [Security Log](docs/SECURITY_LOG.md) - Security decision audit trail
- [Security Exceptions](docs/SECURITY_EXCEPTIONS.md) - Documented exceptions
- [Security Burndown](docs/SECURITY_BURNDOWN.md) - Finding burndown tracking

## Security Practices

This repository implements:

- **Regression-only blocking**: CI fails on new security findings, not pre-existing debt
- **SHA-pinned GitHub Actions**: All workflow actions are pinned by commit SHA
- **Secret safety**: No credentials in code; sanitized logging
- **Default-deny governance**: All code changes require explicit approval or auto-approval rules

## Supported Versions

This is a development tool for personal/internal use. Only the latest version on `main` is supported.

| Version | Supported |
| ------- | --------- |
| main    | Yes       |
| Other   | No        |
