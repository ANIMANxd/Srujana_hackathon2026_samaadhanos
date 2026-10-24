# SamadhaanOS

MSME payment-rights tool for micro and small suppliers in India. It checks
eligibility under the MSMED Act, fixes statutory dates, computes s.16 interest,
shows the buyer's cost of delay, tracks limitation, and drafts a graduated
escalation ladder. Legal math is deterministic and config-driven; the LLM stays
at the edges. Srujana Tech Fest 2026, Legal Services track (LS-03).

Status: **scaffold only.** No engine, no contract, no frontend yet.

## How to run (placeholder)

```
pip install -r requirements.txt
make test      # backend pytest (currently zero tests)
make dev       # backend on http://127.0.0.1:8000 (frontend: not yet implemented)
make fixtures  # copy contracts/fixtures -> frontend/fixtures
make demo      # offline demo mode
```

Full design: `architecture.md`. Agent rules: `AGENTS.md`. This project is
built with AI assistance; see the README's known-limitations section (to be
written by the Docs agent).
