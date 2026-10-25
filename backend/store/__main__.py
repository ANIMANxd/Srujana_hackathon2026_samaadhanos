"""`python -m backend.store` — rebuild and seed the demo database.

Same work as `make db-reset`. Lives in `__main__.py` rather than calling
`seed.py` as a module, because the package `__init__` already imports `seed` and
re-executing it as `__main__` triggers a "found in sys.modules" warning.
"""

from backend.store.seed import main

if __name__ == "__main__":
    raise SystemExit(main())
