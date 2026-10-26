"""Load the statute config for GET /api/v1/config (section 8.1).

This is an I/O concern, so it lives in app/, not engine/. The engine itself
receives config as an explicit argument and never reads files (section 6).
The loader is tolerant on purpose: the demo must run on a laptop with no
statute_config.json present yet (offline-first, principle 5), so a missing
or unparseable file yields a clearly-labelled stub instead of a crash.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.insights.identity import DEFAULT_NAME_MATCH_THRESHOLD

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "statute_config.json"

# The documented fallback for `insights.min_history` (AGENTS.md rule 25). The
# config entry overrides it; this is only what the app uses when the file is
# absent, so a missing config never turns into an invented number.
DEFAULT_MIN_HISTORY = 3

# A stub, not law. Every key from architecture.md section 5 is present so the
# frontend assumptions drawer can render, but nothing here is verified and
# nothing here may be relied on as a statutory value.
_STUB: dict[str, Any] = {
    "_stub": True,
    "_note": (
        "statute_config.json is not present. This is a structural stub so the "
        "assumptions drawer can render. No value here is a statutory value."
    ),
    "interest_multiplier": None,
    "objection_window_days": None,
    "credit_cap_days": None,
    "no_agreement_days": None,
    "bank_rate_epochs": [],
    "size_epochs": [],
    "silpi_test_date": None,
    "trader_nic_prefixes": [],
    "limitation_years": None,
    "section_43bh_first_fy": None,
    "rate_mode_default": None,
    "appropriation_mode_default": None,
    "payment_boundary_convention": None,
    "day_count_fraction_days": None,
    "tax_presets": [],
    "gated_features": {"gst_itc_180d": False, "msme1_return": False, "s19_deposit": False},
    "insights": {
        "value": {
            "name_match_threshold": DEFAULT_NAME_MATCH_THRESHOLD,
            "min_history": DEFAULT_MIN_HISTORY,
        },
        "source_ref": "product setting, not law",
        "verified": False,
        "note": "Stub product settings; no customer book is seeded without the config file.",
    },
}


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Return the statute config dict, or a labelled stub if it is absent."""
    try:
        raw = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return dict(_STUB)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        stub = dict(_STUB)
        stub["_note"] = f"statute_config.json at {path} is not valid JSON; showing stub."
        return stub
    if not isinstance(data, dict):
        stub = dict(_STUB)
        stub["_note"] = f"statute_config.json at {path} is not a JSON object; showing stub."
        return stub
    return data


def objection_window(config: dict[str, Any]) -> tuple[int | None, str | None, bool]:
    """`(days, source_ref, verified)` for the objection window, or all-empty.

    Extraction asks for the window instead of holding a number itself (golden
    rule 4): the tagger needs one to say "late", and the config - not the code -
    is where that number lives. `(None, None, False)` means *cannot be assessed*,
    never "zero days".
    """
    entry = config.get("objection_window_days")
    if isinstance(entry, dict):
        value = entry.get("value")
        if isinstance(value, int) and not isinstance(value, bool):
            source = entry.get("source_ref")
            return value, (str(source) if source else None), bool(entry.get("verified"))
    return None, None, False


@dataclass(frozen=True)
class IdentitySettings:
    """The v5 product settings that shape customer suggestions.

    `verified` is always false for these: they are product choices, not law
    (AGENTS.md rule 27). The source ref says so in plain English.
    """

    name_match_threshold: float
    min_history: int
    source_ref: str | None
    verified: bool


def identity_settings(config: dict[str, Any]) -> IdentitySettings:
    """Read `insights` from the config, with documented fallbacks only.

    A missing or malformed entry must not crash a read-only customer-book screen
    and must not silently become a different threshold. The fallbacks are the
    documented product defaults (0.90 similarity, 3 invoices), and `verified`
    stays false so the UI can label them as product settings.
    """
    entry = config.get("insights")
    value = entry.get("value") if isinstance(entry, dict) else None
    source = entry.get("source_ref") if isinstance(entry, dict) else None
    verified = bool(entry.get("verified")) if isinstance(entry, dict) else False

    threshold = DEFAULT_NAME_MATCH_THRESHOLD
    min_history = DEFAULT_MIN_HISTORY
    if isinstance(value, dict):
        raw_threshold = value.get("name_match_threshold")
        if (
            isinstance(raw_threshold, (int, float))
            and not isinstance(raw_threshold, bool)
            and 0 <= float(raw_threshold) <= 1
        ):
            threshold = float(raw_threshold)
        raw_history = value.get("min_history")
        if (
            isinstance(raw_history, int)
            and not isinstance(raw_history, bool)
            and raw_history >= 1
        ):
            min_history = raw_history

    return IdentitySettings(
        name_match_threshold=threshold,
        min_history=min_history,
        source_ref=str(source) if source else None,
        verified=verified,
    )
