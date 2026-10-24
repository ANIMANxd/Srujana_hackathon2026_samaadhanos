"""Load the statute config for GET /api/v1/config (section 8.1).

This is an I/O concern, so it lives in app/, not engine/. The engine itself
receives config as an explicit argument and never reads files (section 6).
The loader is tolerant on purpose: the demo must run on a laptop with no
statute_config.json present yet (offline-first, principle 5), so a missing
or unparseable file yields a clearly-labelled stub instead of a crash.
"""

import json
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "statute_config.json"

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
