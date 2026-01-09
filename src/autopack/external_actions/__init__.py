"""External actions ledger: durable idempotency + audit trail for side effects.

This module implements the external action ledger described in gap analysis items 6.1 and 6.9:
- Persist idempotency keys and outcomes in DB
- Survive restarts without duplicating side effects
- Query "what happened" for any idempotency key
"""

from .models import ExternalAction, ExternalActionStatus
from .ledger import ExternalActionLedger

__all__ = ["ExternalAction", "ExternalActionStatus", "ExternalActionLedger"]
