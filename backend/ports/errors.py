"""Errors a provider port may raise, so callers do not import `httpx`."""

from __future__ import annotations


class ProviderError(RuntimeError):
    """Base class for a provider that could not complete a call."""


class ProviderUnavailable(ProviderError):
    """The provider could not be reached, or answered with an error.

    Routes should turn this into a `503` with the contract's error envelope, never
    a 500: the supplier has done nothing wrong when a simulated financier is down.
    """
