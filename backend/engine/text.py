"""text.py — small string helpers shared across the engine."""

from typing import Any


def contract_str(value: Any) -> str:
    """The contract's string for `value`: the enum's value, or the string itself.

    Pydantic hands the engine enum members (a `str` subclass whose kind), and
    both `str()` and f-string formatting on one yield `"EvidenceKind.PO"` rather
    than `"PO"`. Everything that is compared, joined, or returned to the
    response must be normalized here first, or a plain-string test passes while
    a real request silently mismatches.

    `value` is expected to be non-null, like the contract fields it represents.
    """
    inner = getattr(value, "value", None)
    return inner if isinstance(inner, str) else str(value)
