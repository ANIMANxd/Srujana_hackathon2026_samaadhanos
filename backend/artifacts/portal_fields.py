"""Portal-field rows for the Stage 4 pack, read from the V10 capture.

The portal's own field list is not something this repo may guess: golden rule 9
forbids fabricating an official form, so the checklist is either the captured
V10 field list or the honest fallback that tells the owner to confirm every
field against the live portal.

Capture format, when V10 lands in `docs/statute-sheet/`:

    docs/statute-sheet/v10_portal_fields.json
    {"captured": true, "source": "screenshot name", "fields": ["Field one", ...]}

Any other situation - no file, `captured` false, no fields, unreadable JSON -
falls back, and the note says which of those happened.
"""

import json
from pathlib import Path
from typing import Sequence

STATUTE_SHEET = Path(__file__).resolve().parents[2] / "docs" / "statute-sheet"
CAPTURE_PREFIX = "v10"

FALLBACK_ROWS: tuple[str, ...] = (
    "The portal's field list, order and format - to be confirmed against the live portal",
    "Which value from this pack belongs in which field - to be confirmed against the live portal",
    "Any document the portal asks you to attach - to be confirmed against the live portal",
    "The portal's own instructions for this form - to be confirmed against the live portal",
)

FALLBACK_NOTE = (
    "The V10 capture - the portal's own field list - is not in this repo's statute sheet "
    "yet, so no field name, order or format is asserted here."
)


def portal_checklist() -> tuple[str, Sequence[str]]:
    """(note, checkbox rows) for the pack's portal-fields section."""
    capture = _load_capture()
    if capture is None:
        return FALLBACK_NOTE, [f"- [ ] {row}" for row in FALLBACK_ROWS]
    if not capture.get("captured") or not capture.get("fields"):
        return (
            f"{FALLBACK_NOTE} A capture file ({capture.get('_file')}) exists but does not "
            "read as captured yet.",
            [f"- [ ] {row}" for row in FALLBACK_ROWS],
        )
    source = capture.get("source")
    note = (
        f"Field list read from the V10 capture ({capture['_file']}"
        + (f", {source}" if source else "")
        + "). Confirm each entry against the live portal before filing."
    )
    return note, [f"- [ ] {field}" for field in capture["fields"]]


def _load_capture() -> dict | None:
    """The first V10 capture JSON in the statute sheet, or None when absent."""
    if not STATUTE_SHEET.is_dir():
        return None
    for path in sorted(STATUTE_SHEET.glob("*.json")):
        if not path.name.lower().startswith(CAPTURE_PREFIX):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"_file": path.name, "captured": False}
        if not isinstance(data, dict):
            return {"_file": path.name, "captured": False}
        data["_file"] = path.name
        return data
    return None
