"""Adapters: the concrete side of `backend/ports/`.

- `mock/` — HTTP to the simulated provider service on :8100 (labelled simulation).
- `live/` — stubs that raise `NotImplementedError("live provider not integrated")`.
- `clock.py`, `ids.py` — time and identity, so workflow code never reads them itself.

Wiring and the production guard live in `backend/app/deps.py`.
"""

from backend.adapters.clock import OffsetClock, SystemClock
from backend.adapters.ids import SeededIdGenerator, UlidIdGenerator

__all__ = ["OffsetClock", "SeededIdGenerator", "SystemClock", "UlidIdGenerator"]
