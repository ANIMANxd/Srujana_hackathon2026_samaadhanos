"""eSign provider port (architecture_v4 section 6).

Completion never arrives through these methods: it arrives as a **signed webhook**
to `POST /api/v1/webhooks/esign`. `get_session` exists for a UI that wants to poll
a pending session, not as the source of truth.

There is no Aadhaar field anywhere in this contract, and there never will be
(golden rule 18). A `SignerRef` carries a display name and optional contact
details only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from backend.app.schemas_v4 import ESignSession


@dataclass(frozen=True)
class SignableDoc:
    """The document a signer is asked to sign.

    `doc_sha256` is the hash of the exact bytes, so the signed copy can be checked
    against what was shown (architecture_v4 section 7.1).
    """

    doc_id: str
    doc_sha256: str
    title: str
    url: str | None = None


@dataclass(frozen=True)
class SignerRef:
    """Who signs. Contact details are optional and personal data (mask in logs)."""

    display_name: str
    phone: str | None = None
    email: str | None = None


@runtime_checkable
class ESignProvider(Protocol):
    """A licensed eSign service, or a labelled simulation of one."""

    simulated: bool

    def create_session(self, doc: SignableDoc, signer: SignerRef, idem_key: str) -> ESignSession:
        """Start a signing session. Idempotent on `idem_key`."""
        ...

    def get_session(self, session_id: str) -> ESignSession:
        """Read a session's current status."""
        ...
