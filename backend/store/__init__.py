"""v4 persistence layer: tables, audit chain, idempotency, demo seed.

The engine stays stateless. This package stores the inputs and the responses the
engine produced; it computes no legal number itself.
"""

from backend.store.audit import append_event, event_count, event_hash, verify_chain
from backend.store.db import (
    DEFAULT_DATABASE_URL,
    database_file,
    database_url,
    dispose,
    init_db,
    reset_db,
    session_scope,
)
from backend.store.idempotency import IdempotentResult, get_or_store, hash_request
from backend.store.ids import deterministic_ulid, is_ulid, new_ulid
from backend.store.models import (
    Bid,
    Case,
    Evaluation,
    Event,
    FinancingRequest,
    IdempotencyKey,
    Track,
    WebhookInbox,
)
from backend.store.seed import reset_and_seed, seed_presets

__all__ = [
    "DEFAULT_DATABASE_URL",
    "Bid",
    "Case",
    "Evaluation",
    "Event",
    "FinancingRequest",
    "IdempotencyKey",
    "IdempotentResult",
    "Track",
    "WebhookInbox",
    "append_event",
    "database_file",
    "database_url",
    "deterministic_ulid",
    "dispose",
    "event_count",
    "event_hash",
    "get_or_store",
    "hash_request",
    "init_db",
    "is_ulid",
    "new_ulid",
    "reset_and_seed",
    "reset_db",
    "seed_presets",
    "session_scope",
    "verify_chain",
]
