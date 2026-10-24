"""env.py — the single place the engine may read the environment.

Section 6 requires backend/engine/ to stay pure: no I/O, no clock, no network.
Reading an env var is I/O, so it is quarantined here and only for the one flag
the architecture explicitly names (STRICT_VERIFIED, section 5). Import this from
the application entrypoints; never import it from a rule module, and never call
it from inside a calculation.
"""

import os


def strict_verified_enabled() -> bool:
    """True when STRICT_VERIFIED is set to a truthy value ("1", "true", "yes").

    Run this before the demo video (section 5): it turns every UNVERIFIED_CONSTANT
    warning into a hard error, so no unverified statutory number reaches screen.
    """
    return os.environ.get("STRICT_VERIFIED", "").strip().lower() in {"1", "true", "yes"}
