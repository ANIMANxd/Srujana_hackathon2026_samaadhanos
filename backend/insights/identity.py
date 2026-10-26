"""Pure customer-identity maths for the v5 Customer book.

No I/O, no clock and no randomness: the caller passes the customer snapshot in
and gets a decision back. Persistence lives in `backend/store/customers.py`;
this module never touches a database or the network.

**GSTIN validation is format only.** The 15-character pattern from the GSTIN
format is checked; the check digit is not verified, and no GST portal lookup is
made. An invalid GSTIN is never silently dropped: `resolve()` returns a
PROVISIONAL customer plus a warning saying the format did not match.

Identity rules:

- A valid GSTIN's characters 3-12 are its PAN (1-indexed). The same PAN is the
  same legal entity, so two state registrations group automatically.
- Different PANs are **never** merged. `suggestions()` may say
  `LINK_AS_GROUP`, which is an owner action, not a merge.
- A buyer with no usable GSTIN is PROVISIONAL: matched by an exact normalised
  name among provisional rows that carry no GSTIN, else created.
- Suggestions are only suggestions. Nothing here applies one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, TypedDict

from rapidfuzz import fuzz

PAN_KIND = "PAN"
PROVISIONAL_KIND = "PROVISIONAL"
ATTACH_SUGGESTION = "ATTACH"
LINK_AS_GROUP_SUGGESTION = "LINK_AS_GROUP"

# A product setting, not law. The wiring reads `insights.name_match_threshold`
# from the config; this value is only the documented fallback for direct calls.
DEFAULT_NAME_MATCH_THRESHOLD = 0.90

# The GSTIN pattern. It is deliberately structural: the final check character
# is matched as a character, not recomputed.
GSTIN_PATTERN = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$", re.ASCII
)

_M_S_PREFIX = re.compile(r"^\s*M\s*/\s*S\.?\s*", re.IGNORECASE)
_PUNCTUATION = re.compile(r"[^\w\s]|_", re.UNICODE)

# Token-level legal-form mappings. Applied after punctuation removal, so
# "PVT." and "LTD." have already become "PVT" and "LTD".
_LEGAL_FORM_TOKENS: dict[str, str] = {
    "PVT": "PRIVATE",
    "PRIVATE": "PRIVATE",
    "LTD": "LIMITED",
    "LIMITED": "LIMITED",
    "CO": "COMPANY",
}


class GstinCheck(TypedDict):
    """The shape of `validate_gstin`'s answer."""

    ok: bool
    reason: str


class Suggestion(TypedDict):
    """One owner-facing suggestion. It is never applied automatically."""

    a: str
    b: str
    kind: str
    similarity: float
    reason: str


def _clean_gstin(gstin: str | None) -> str:
    if not isinstance(gstin, str):
        return ""
    return gstin.strip().upper()


def _clean_display_name(name: str | None) -> str:
    """Keep the owner's words, only trimming and collapsing whitespace."""
    if not isinstance(name, str):
        return ""
    return " ".join(name.split())


def validate_gstin(gstin: str | None) -> GstinCheck:
    """Check the 15-character GSTIN format only (the check digit is not verified).

    Input is trimmed and uppercased first, so `27abcde1234f1z5` is accepted.
    An empty or non-string value is a clean `ok: False`, never an exception.
    """
    value = _clean_gstin(gstin)
    if not value:
        return {"ok": False, "reason": "No GSTIN was entered."}
    if GSTIN_PATTERN.fullmatch(value) is not None:
        return {
            "ok": True,
            "reason": (
                "Valid GSTIN format (format only; the check digit is not verified)."
            ),
        }
    return {
        "ok": False,
        "reason": (
            f"GSTIN {value!r} is not in the 15-character format "
            "(2 digits, 5 letters, 4 digits, 1 letter, an entity code, Z and a "
            "check character). It was kept as a provisional buyer with a warning."
        ),
    }


def pan_from_gstin(gstin: str | None) -> str | None:
    """Characters 3 to 12 of a valid GSTIN (1-indexed), else None.

    `27ABCDE1234F1Z5` -> `ABCDE1234F`. The full GSTIN format is checked first;
    an invalid value never yields a PAN.
    """
    value = _clean_gstin(gstin)
    if GSTIN_PATTERN.fullmatch(value) is None:
        return None
    return value[2:12]


def normalize_name(name: str | None) -> str:
    """A comparison key for a business name.

    Uppercase, a leading ``M/S`` / ``M/S.`` removed, punctuation removed, ``&``
    expanded to ``AND``, whitespace collapsed, and the legal-form tokens mapped
    (PVT/PVT./PRIVATE -> PRIVATE, LTD/LTD./LIMITED -> LIMITED, CO -> COMPANY).
    Legal suffixes are **not** removed: "ACME PRIVATE LIMITED" and "ACME" stay
    different keys. A similar-but-different name is a suggestion, never a merge.
    """
    if not isinstance(name, str):
        return ""
    text = name.upper()
    text = _M_S_PREFIX.sub("", text, count=1)
    text = text.replace("&", " AND ")
    text = _PUNCTUATION.sub(" ", text)
    tokens = [_LEGAL_FORM_TOKENS.get(token, token) for token in text.split()]
    return " ".join(tokens)


@dataclass(frozen=True)
class CustomerRecord:
    """One customer as the pure functions see it, without a database session.

    `normalized_name` is recomputed from `display_name` when omitted, so a test
    or caller cannot accidentally compare a raw name. `gstins` are trimmed and
    uppercased; `dismissed_with` holds the ids of customers whose merge
    suggestion the owner dismissed.
    """

    id: str
    kind: str
    pan: str | None = None
    normalized_name: str = ""
    display_name: str = ""
    gstins: tuple[str, ...] = ()
    group_id: str | None = None
    dismissed_with: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        kind = (self.kind or "").strip().upper()
        if kind not in (PAN_KIND, PROVISIONAL_KIND):
            raise ValueError(
                f"customer kind must be {PAN_KIND!r} or {PROVISIONAL_KIND!r}, "
                f"got {self.kind!r}"
            )
        pan = (
            self.pan.strip().upper()
            if isinstance(self.pan, str) and self.pan.strip()
            else None
        )
        if kind == PAN_KIND and pan is None:
            raise ValueError("a PAN-kind customer needs a PAN")
        if kind == PROVISIONAL_KIND and pan is not None:
            raise ValueError("a PROVISIONAL customer cannot carry a PAN")
        normalized = normalize_name(self.normalized_name or self.display_name)
        gstins = tuple(
            sorted({cleaned for value in self.gstins if (cleaned := _clean_gstin(value))})
        )
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "pan", pan)
        object.__setattr__(self, "normalized_name", normalized)
        object.__setattr__(self, "gstins", gstins)
        object.__setattr__(self, "dismissed_with", frozenset(self.dismissed_with))


@dataclass(frozen=True)
class Resolution:
    """What identity resolution decided, ready for the store to persist.

    `key` is the stable customer key: ``PAN:<pan>`` for a legal entity,
    ``NAME:<normalised name>`` for a name-only provisional, ``GSTIN:<gstin>``
    for a provisional known only by an unformatted GSTIN, and ``UNNAMED`` when
    neither a name nor a GSTIN was supplied. `create` means no existing record
    matched; `attach_gstin` means the GSTIN should be stored under the customer.
    """

    key: str
    customer_id: str | None
    kind: str
    pan: str | None
    normalized_name: str
    display_name: str
    gstin: str | None
    create: bool
    attach_gstin: bool
    promote_to_pan: bool
    warnings: tuple[str, ...] = ()


def _find_by_gstin(records: Iterable[CustomerRecord], gstin: str) -> CustomerRecord | None:
    for record in records:
        if gstin in record.gstins:
            return record
    return None


def _find_by_pan(records: Iterable[CustomerRecord], pan: str) -> CustomerRecord | None:
    for record in records:
        if record.kind == PAN_KIND and record.pan == pan:
            return record
    return None


def _find_provisional_by_name(
    records: Iterable[CustomerRecord], normalized_name: str
) -> CustomerRecord | None:
    """The oldest PROVISIONAL row with this exact normalised name.

    A provisional has no PAN by definition, so a name is the only identity it
    can offer. A GSTIN on a provisional row is unformatted data, not a second
    legal identity; the caller's first match wins when the input is ordered by
    creation time.
    """
    if not normalized_name:
        return None
    for record in records:
        if record.kind == PROVISIONAL_KIND and record.normalized_name == normalized_name:
            return record
    return None


def _provisional_key(*, normalized_name: str, gstin: str | None) -> str:
    if normalized_name:
        return f"NAME:{normalized_name}"
    if gstin:
        return f"GSTIN:{gstin}"
    return "UNNAMED"


def _existing_resolution(
    record: CustomerRecord,
    *,
    key: str,
    kind: str,
    pan: str | None,
    gstin: str | None,
    attach_gstin: bool,
    promote_to_pan: bool,
    warnings: tuple[str, ...],
) -> Resolution:
    return Resolution(
        key=key,
        customer_id=record.id,
        kind=kind,
        pan=pan,
        normalized_name=record.normalized_name,
        display_name=record.display_name,
        gstin=gstin,
        create=False,
        attach_gstin=attach_gstin,
        promote_to_pan=promote_to_pan,
        warnings=warnings,
    )


def resolve(
    buyer_gstin: str | None,
    buyer_name: str | None,
    existing: Iterable[CustomerRecord],
) -> Resolution:
    """Resolve one buyer's details to a customer decision.

    A valid GSTIN wins and maps to the PAN customer (existing or new). An invalid
    or absent GSTIN maps to a PROVISIONAL customer by normalised name; an invalid
    GSTIN is kept on the resolution with a warning rather than discarded.
    """
    records = tuple(existing)
    gstin = _clean_gstin(buyer_gstin)
    name = _clean_display_name(buyer_name)
    normalized = normalize_name(name)
    warnings: list[str] = []

    check = validate_gstin(gstin) if gstin else None
    if check is not None and not check["ok"]:
        warnings.append(check["reason"])

    if gstin and check is not None and check["ok"]:
        pan = pan_from_gstin(gstin)
        if pan is None:  # defensive: a valid pattern always yields a PAN
            raise ValueError(f"valid GSTIN {gstin!r} did not yield a PAN")

        by_gstin = _find_by_gstin(records, gstin)
        if by_gstin is not None:
            if by_gstin.kind == PAN_KIND:
                if by_gstin.pan != pan:
                    warnings.append(
                        f"GSTIN {gstin} carries PAN {pan}, but the existing customer "
                        f"{by_gstin.id} has PAN {by_gstin.pan}. The existing identity "
                        "was kept; this needs owner review."
                    )
                return _existing_resolution(
                    by_gstin,
                    key=f"PAN:{by_gstin.pan}",
                    kind=PAN_KIND,
                    pan=by_gstin.pan,
                    gstin=gstin,
                    attach_gstin=False,
                    promote_to_pan=False,
                    warnings=tuple(warnings),
                )

            # A valid GSTIN on a provisional row: promote it, unless a PAN
            # customer already exists. Promoting then would create two customers
            # with one PAN and break the identity rule.
            pan_owner = _find_by_pan(records, pan)
            if pan_owner is not None and pan_owner.id != by_gstin.id:
                warnings.append(
                    f"GSTIN {gstin} is attached to provisional customer "
                    f"{by_gstin.id}, but PAN {pan} already belongs to customer "
                    f"{pan_owner.id}. The case was attached to the PAN customer; "
                    "the stale GSTIN link needs owner review."
                )
                return _existing_resolution(
                    pan_owner,
                    key=f"PAN:{pan}",
                    kind=PAN_KIND,
                    pan=pan,
                    gstin=gstin,
                    attach_gstin=False,
                    promote_to_pan=False,
                    warnings=tuple(warnings),
                )
            return Resolution(
                key=f"PAN:{pan}",
                customer_id=by_gstin.id,
                kind=PAN_KIND,
                pan=pan,
                normalized_name=by_gstin.normalized_name or normalized,
                display_name=by_gstin.display_name or name or f"Buyer ({pan})",
                gstin=gstin,
                create=False,
                attach_gstin=False,
                promote_to_pan=True,
                warnings=tuple(warnings),
            )

        by_pan = _find_by_pan(records, pan)
        if by_pan is not None:
            return _existing_resolution(
                by_pan,
                key=f"PAN:{pan}",
                kind=PAN_KIND,
                pan=pan,
                gstin=gstin,
                attach_gstin=True,
                promote_to_pan=False,
                warnings=tuple(warnings),
            )

        return Resolution(
            key=f"PAN:{pan}",
            customer_id=None,
            kind=PAN_KIND,
            pan=pan,
            normalized_name=normalized,
            display_name=name or f"Buyer ({pan})",
            gstin=gstin,
            create=True,
            attach_gstin=True,
            promote_to_pan=False,
            warnings=tuple(warnings),
        )

    # Invalid or absent GSTIN: a provisional identity.
    if gstin:
        by_gstin = _find_by_gstin(records, gstin)
        if by_gstin is not None:
            return _existing_resolution(
                by_gstin,
                key=_provisional_key(
                    normalized_name=by_gstin.normalized_name, gstin=gstin
                ),
                kind=PROVISIONAL_KIND,
                pan=None,
                gstin=gstin,
                attach_gstin=False,
                promote_to_pan=False,
                warnings=tuple(warnings),
            )

    by_name = _find_provisional_by_name(records, normalized)
    if by_name is not None:
        return _existing_resolution(
            by_name,
            key=f"NAME:{by_name.normalized_name}",
            kind=PROVISIONAL_KIND,
            pan=None,
            gstin=gstin or None,
            attach_gstin=bool(gstin),
            promote_to_pan=False,
            warnings=tuple(warnings),
        )

    if not normalized and not gstin:
        warnings.append(
            "No buyer name or GSTIN was entered; this case gets its own "
            "provisional customer."
        )

    return Resolution(
        key=_provisional_key(normalized_name=normalized, gstin=gstin or None),
        customer_id=None,
        kind=PROVISIONAL_KIND,
        pan=None,
        normalized_name=normalized,
        display_name=name or ("Unnamed buyer" if not gstin else f"Buyer ({gstin})"),
        gstin=gstin or None,
        create=True,
        attach_gstin=bool(gstin),
        promote_to_pan=False,
        warnings=tuple(warnings),
    )


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return fuzz.token_sort_ratio(left, right) / 100.0


def suggestions(
    customers: Iterable[CustomerRecord],
    *,
    threshold: float = DEFAULT_NAME_MATCH_THRESHOLD,
) -> list[Suggestion]:
    """Suggest owner actions for similar customer names. Never mutates anything.

    - ``ATTACH``: a PROVISIONAL customer and a PAN customer whose names score at
      least `threshold`, so the provisional can be attached to the legal entity.
    - ``LINK_AS_GROUP``: two PAN customers with similar names but different PANs.
      They are never merged; the owner may link them as a group.

    Pairs already in the same group and pairs in `dismissed_with` are excluded.
    Similarity is `rapidfuzz.fuzz.token_sort_ratio / 100` on normalised names.
    `threshold` should be `insights.name_match_threshold` from the config; the
    default is only the documented product fallback.
    """
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise TypeError("threshold must be a number between 0 and 1")
    if not 0 <= float(threshold) <= 1:
        raise ValueError("threshold must be between 0 and 1")

    records = tuple(customers)
    found: list[Suggestion] = []
    for left, right in combinations(records, 2):
        if left.id == right.id:
            continue
        if right.id in left.dismissed_with or left.id in right.dismissed_with:
            continue
        if left.group_id is not None and left.group_id == right.group_id:
            continue

        if {left.kind, right.kind} == {PROVISIONAL_KIND, PAN_KIND}:
            provisional = left if left.kind == PROVISIONAL_KIND else right
            pan_customer = right if provisional is left else left
            score = _similarity(
                provisional.normalized_name, pan_customer.normalized_name
            )
            if score >= threshold:
                found.append(
                    {
                        "a": provisional.id,
                        "b": pan_customer.id,
                        "kind": ATTACH_SUGGESTION,
                        "similarity": score,
                        "reason": (
                            f"'{provisional.display_name or provisional.id}' and "
                            f"'{pan_customer.display_name or pan_customer.id}' have "
                            f"matching names ({score:.2f}). Attaching the provisional "
                            "record to the PAN customer keeps the PAN as the legal "
                            "identity. Suggestion only."
                        ),
                    }
                )
            continue

        if left.kind == PAN_KIND and right.kind == PAN_KIND:
            if left.pan == right.pan:
                # A valid book has one customer per PAN; this is corrupt data,
                # not a group-to-link suggestion.
                continue
            score = _similarity(left.normalized_name, right.normalized_name)
            if score >= threshold:
                a, b = sorted((left.id, right.id))
                found.append(
                    {
                        "a": a,
                        "b": b,
                        "kind": LINK_AS_GROUP_SUGGESTION,
                        "similarity": score,
                        "reason": (
                            f"'{left.display_name or left.id}' and "
                            f"'{right.display_name or right.id}' have similar names "
                            f"({score:.2f}) but different PANs. Link them as a group; "
                            "never merge different PANs. Suggestion only."
                        ),
                    }
                )

    found.sort(key=lambda item: (-item["similarity"], item["kind"], item["a"], item["b"]))
    return found
