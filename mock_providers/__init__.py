"""Mock provider service. **SIMULATION ONLY.**

Run it on its own:

    python -m uvicorn mock_providers.app:app --port 8100 --app-dir .

Nothing here is real: no money moves, no signature is legal, and there is no Aadhaar
field anywhere in this package. Every identifier is `MOCK`-prefixed, and every
financier name is fictional (Financier A/B/C).

Why it exists: the API's webhook pipeline is only worth having if something actually
exercises it. This service signs real HMAC deliveries, retries non-2xx with backoff
and dead-letters what never lands, so dedupe, parking and replay protection are
tested by traffic rather than by a mock of traffic.

`__init__` deliberately does not import `app`: the routers import this package, so
importing the app here would be circular.
"""
