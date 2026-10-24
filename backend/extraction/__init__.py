"""Extraction: turn an uploaded text file into *suggestions* a human confirms.

This package is the edge (architecture.md principle 1: LLM at the edges, law at
the core). It reads no statute config of its own - the route passes what it
needs - it computes no legal number, and **the legal engine never imports it**
(tested in `backend/tests/contract/test_extraction.py`): everything it produces
is a machine-suggested candidate with a line citation and a confidence, and
nothing reaches `CaseEvaluationRequest` until a person confirms it.

Paths, in order of preference:

1. **Regex and keyword first** (`whatsapp.py`, `fields.py`) - deterministic,
   offline, no network. This is what the demo runs.
2. **Optional LLM layer** (`llm.py`) - only when the env flags are set, only to
   fill fields the regex path could not read, same output schema, and any
   failure falls back to the regex result untouched. Never required.
3. **Cached demo mode** (`cache.py`) - `EXTRACTION_DEMO_CACHE=1` returns the
   prepared result stored for that exact text, with no network at all.

Environment flags (read by the route, never at import time):

- `EXTRACTION_LLM=1` plus `EXTRACTION_LLM_URL=<endpoint>` enables the LLM layer.
- `EXTRACTION_DEMO_CACHE=1` enables the demo cache (read and write).

Regenerate the committed cache after changing the regex path:

    python -m backend.extraction.cache_build
"""

# The package __init__ imports nothing: `backend.app.schemas` reads
# `backend.extraction.tags`, and importing the pipeline from here would close
# that loop. Import the entry point directly instead:
#
#     from backend.extraction.extract import extract_evidence
