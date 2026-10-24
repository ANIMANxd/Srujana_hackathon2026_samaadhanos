"""Regenerate the committed demo cache from the regex path.

    python -m backend.extraction.cache_build

The files in `cache/` are generated, never hand-written (golden rule 7): each
one is the extractors' own output for the matching file in `demo/`, stored so
the demo can answer with no network at all. Change an extractor and re-run this
before committing, or the freshness test in `tests/contract/test_extraction.py`
fails the same way a stale fixture would.
"""

from backend.app.config_loader import load_config, objection_window
from backend.extraction import cache
from backend.extraction.extract import extract_evidence
from backend.extraction.text import decode_text


def build() -> list[str]:
    """Cache every demo text. Returns the file names written, in order."""
    window, source_ref, verified = objection_window(load_config())
    written: list[str] = []
    for path in sorted(cache.DEMO_DIR.glob("*.txt")):
        raw = path.read_bytes()
        response = extract_evidence(
            raw=raw,
            objection_window_days=window,
            window_source_ref=source_ref,
            window_verified=verified,
            use_cache=False,  # a build run must never read what it is writing
            llm=None,  # the cache records the regex path, never a model's answer
        )
        cache.store(path.name, decode_text(raw).text, response.model_dump(mode="json"))
        written.append(path.name)
    return written


if __name__ == "__main__":
    for name in build():
        print(f"cached {name}")
