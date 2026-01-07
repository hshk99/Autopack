"""
Integration Runner - Safe external side-effect execution (BUILD-189 Phase 5 Skeleton)

This module provides a standardized way to execute external integrations with:
- Timeouts and retry policies
- Idempotency keys to prevent duplicate actions
- Per-provider rate limiting
- Structured audit logging

Goals:
- Safe by default (bounded actions, no credential leaks)
- Auditable (every action logged with correlation ID)
- Resumable (idempotency keys enable safe retries)

Providers:
- Etsy shop management
- Shopify store operations
- YouTube video management
- Trading broker execution
"""

from .runner import IntegrationRunner, IntegrationResult

__all__ = ["IntegrationRunner", "IntegrationResult"]
