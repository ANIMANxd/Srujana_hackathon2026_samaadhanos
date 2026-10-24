"""Demo cache: a prepared extraction result stored against the exact text.

Cache mode is opt-in (`EXTRACTION_DEMO_CACHE=1`) and keyed by the SHA-256 of
the decoded text, so it can only ever answer for text it was generated from -
a one-character difference misses and the regex path runs as usual.

The stored results are **generated, never hand-written**: `cache_build.py` runs
the regex path over `demo/*.txt` and writes what it produces, and
`backend/tests/contract/test_extraction.py` fails if a stored result drifts
from what the code would produce now (the same freshness rule as the fixtures).
"""

import hashlib
import json
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent / "cache"
DEMO_DIR = Path(__file__).resolve().parent / "demo"


def cache_key(text: str) -> str:
    """Short, stable key for one exact text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def load(text: str) -> dict | None:
    """The stored response for this text, or None (any read failure counts)."""
    path = CACHE_DIR / f"{cache_key(text)}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    response = data.get("response") if isinstance(data, dict) else None
    return response if isinstance(response, dict) else None


def store(name: str, text: str, response: dict) -> Path:
    """Write one generated result. Called only by `cache_build`."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{cache_key(text)}.json"
    payload = {
        "generated_from": name,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "response": response,
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path
