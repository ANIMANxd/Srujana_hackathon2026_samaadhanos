"""The optional LLM layer: same output schema, never required, always behind a flag.

Design rules, so this layer can never become load-bearing:

- It is only consulted when `EXTRACTION_LLM=1` **and** `EXTRACTION_LLM_URL` are
  set. With no flag there is no client, no socket, no import-time env read.
- It only **fills keys the regex path left `missing`**. A regex hit is
  deterministic, citeable to a line, and never overwritten by a guess.
- Any failure - timeout, non-JSON, 5xx, no URL - returns `None` and the regex
  result stands unchanged, so an offline demo behaves exactly as before.
- Message tagging stays regex-only: a tag must carry a line number and a date
  arithmetic the model cannot see, and the engine re-derives every objection
  later from the confirmed dates anyway.
- Everything it produces is still `machine_suggested`; the method changes to
  `llm` so the review screen can show where a value came from.
"""

import json
import urllib.request
from dataclasses import dataclass
from typing import Callable, Mapping

from backend.app.schemas import ExtractedField, ExtractionMethod
from backend.extraction.tags import FIELD_KEYS

DEFAULT_TIMEOUT = 5.0
MAX_CHARS = 20_000
# An answer with no confidence of its own is shown as a middle-of-the-road
# guess. This is a display heuristic for one column, not a legal value.
DEFAULT_LLM_CONFIDENCE = 0.65

Transport = Callable[["LlmSettings", dict], "Mapping | None"]


@dataclass(frozen=True)
class LlmSettings:
    """What the route read from the environment: nothing else is consulted."""

    url: str
    timeout: float = DEFAULT_TIMEOUT
    max_chars: int = MAX_CHARS


def settings_from_env(env: Mapping[str, str]) -> LlmSettings | None:
    """The flag pair, read once by the route. Off means genuinely off."""
    flag = env.get("EXTRACTION_LLM", "").strip().lower()
    if flag not in ("1", "true", "yes", "on"):
        return None
    url = env.get("EXTRACTION_LLM_URL", "").strip()
    if not url:
        return None
    return LlmSettings(url=url)


def post_json(settings: LlmSettings, payload: dict) -> Mapping | None:
    """One POST, offline-tolerant: any failure is just `None`.

    Kept tiny and dependency-free (urllib) so the layer adds no package and
    cannot break an install. The demo never sets the flag, so this never runs.
    """
    request = urllib.request.Request(
        settings.url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.timeout) as response:
            body = response.read()
        parsed = json.loads(body.decode("utf-8"))
    except Exception:  # noqa: BLE001 - every failure degrades to the regex result
        return None
    return parsed if isinstance(parsed, Mapping) else None


def suggest(
    settings: LlmSettings | None,
    *,
    text: str,
    source_kind: str,
    transport: Transport | None = None,
) -> Mapping | None:
    """Ask for field suggestions, or return None so the caller stays on regex."""
    if settings is None:
        return None
    send = transport or post_json
    return send(settings, {"text": text[: settings.max_chars], "kind": source_kind})


def apply_llm(fields: dict[str, ExtractedField], payload: Mapping | None) -> int:
    """Fill `missing` fields from an LLM answer. Returns how many were filled."""
    if not payload:
        return 0
    suggestions = payload.get("fields")
    if not isinstance(suggestions, Mapping):
        return 0

    filled = 0
    for key in FIELD_KEYS:
        current = fields.get(key)
        if current is None or current.method != ExtractionMethod.MISSING:
            continue
        entry = suggestions.get(key)
        if not isinstance(entry, Mapping):
            continue
        value = entry.get("value")
        if not isinstance(value, str) or not value.strip():
            continue
        fields[key] = ExtractedField(
            value=value.strip(),
            source_text=_str_or_none(entry.get("source_text")),
            page=None,
            line=_int_or_none(entry.get("line")),
            method=ExtractionMethod.LLM,
            confidence=_confidence(entry.get("confidence")),
            machine_suggested=True,
        )
        filled += 1
    return filled


def _str_or_none(value) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _int_or_none(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _confidence(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return DEFAULT_LLM_CONFIDENCE
    return round(min(1.0, max(0.0, float(value))), 2)
