"""Stage 1-4 artifact templates: markdown drafts plus an optional PDF (A2/A3).

This package turns a `CaseEvaluationResponse` into a document. It reads the
engine's output and the request's inputs and prints them - it computes no legal
number itself (AGENTS.md golden rule 6), reads no clock, and sends nothing
anywhere (golden rule 10).

The package `__init__` deliberately imports nothing: `backend.app.schemas`
reads `backend.artifacts.kinds`, and importing the templates from here would
close that loop. Import the entry point directly instead:

    from backend.artifacts.generate import build_artifact
"""
