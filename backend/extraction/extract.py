"""The extraction entry point: decode, detect, extract, tag, cite, warn.

Order of work, and why:

1. **Decode** (`text.py`) - encoding, size and binary guards, all offline.
2. **Cache** - in demo mode an exact-text hit returns the prepared result and
   stops here, so the demo never needs anything else.
3. **Detect** - a WhatsApp-shaped header line makes this an export, otherwise
   plain document text. Detection is a property of the text, not a flag.
4. **Extract fields** (label-anchored regex) and **parse + tag messages**
   (keywords plus the window). Every candidate carries its line number.
5. **Optional LLM fill** - only for keys the regex path left `missing`, only
   when the flags say so, and a failure changes nothing else.
6. **Warn** - what was assumed (date order, the configured window, the
   encoding), what could not be assessed (anchor, window), and that every
   single value here is machine-suggested until a human confirms it.

The result is `ExtractionResponse`: suggestions with citations, plus the
confirm schema that maps each one onto a `CaseEvaluationRequest` path. Nothing
in this module is reachable from the engine, and nothing here evaluates a case.
"""

from datetime import date

from backend.app.schemas import (
    CONTRACT_VERSION,
    ConfirmEntry,
    ConfirmFieldType,
    ConfirmKind,
    ExtractedField,
    ExtractedMessage,
    ExtractionMethod,
    ExtractionResponse,
    Warning,
)
from backend.extraction import cache as cache_store
from backend.extraction.confirm import CONFIRM_SCHEMA
from backend.extraction.fields import FieldHit, extract_fields
from backend.extraction.llm import LlmSettings, Transport, apply_llm, suggest
from backend.extraction.tags import FIELD_KEYS, SourceKind
from backend.extraction.text import decode_text
from backend.extraction.whatsapp import (
    ambiguous_header_dates,
    delivery_anchor,
    looks_like_whatsapp,
    parse_messages,
    tag_messages,
)

# A value read out of a conversation is weaker than the same value read off the
# invoice itself, so chat-sourced fields show a lower confidence. Display
# heuristic for one column, not a legal value.
CHAT_FIELD_PENALTY = 0.10

# Warning codes (stable, i18n-friendly like the engine's).
WARN_MACHINE_SUGGESTED = "MACHINE_SUGGESTED"
WARN_FILE_ENCODING = "FILE_ENCODING"
WARN_DATE_ORDER = "DATE_ORDER_ASSUMED"
WARN_WINDOW_APPLIED = "OBJECTION_WINDOW_APPLIED"
WARN_WINDOW_MISSING = "OBJECTION_WINDOW_UNAVAILABLE"
WARN_NO_ANCHOR = "DELIVERY_ANCHOR_MISSING"
WARN_NO_CANDIDATES = "NO_CANDIDATES"
WARN_LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
WARN_LLM_FILLED = "LLM_FILLED"
WARN_CACHE_HIT = "CACHE_HIT"


def extract_evidence(
    *,
    raw: bytes,
    objection_window_days: int | None = None,
    window_source_ref: str | None = None,
    window_verified: bool = False,
    use_cache: bool = False,
    llm: LlmSettings | None = None,
    llm_transport: Transport | None = None,
) -> ExtractionResponse:
    """Turn one uploaded text into machine-suggested, line-cited candidates.

    `objection_window_days` is passed in from statute config by the caller: the
    tagger holds no statutory number of its own, and `None` means "cannot
    assess", never "zero days".
    """
    decoded = decode_text(raw)
    lines = decoded.lines

    if use_cache:
        stored = cache_store.load(decoded.text)
        if stored is not None:
            response = ExtractionResponse.model_validate(stored)
            response.cache_hit = True
            response.warnings.append(
                Warning(
                    code=WARN_CACHE_HIT,
                    severity="INFO",
                    text=(
                        "A prepared result stored for this exact text was returned "
                        "(demo cache). Regenerate it after a change to the "
                        "extractors: python -m backend.extraction.cache_build."
                    ),
                )
            )
            return response

    kind = (
        SourceKind.WHATSAPP_EXPORT
        if looks_like_whatsapp(lines)
        else SourceKind.DOCUMENT_TEXT
    )
    hits = extract_fields(lines)
    fields = _field_objects(
        hits, CHAT_FIELD_PENALTY if kind == SourceKind.WHATSAPP_EXPORT else 0.0
    )
    supplier_name = hits["supplier_name"].value if "supplier_name" in hits else None

    warnings: list[Warning] = [
        Warning(
            code=WARN_MACHINE_SUGGESTED,
            severity="INFO",
            text=(
                "Every value and tag in this response was suggested by a machine "
                "from the uploaded text, with a line citation and a confidence. "
                "Nothing reaches a case evaluation until a person confirms it; "
                "the engine never calls this module."
            ),
        )
    ]
    if decoded.encoding_was_guessy:
        warnings.append(
            Warning(
                code=WARN_FILE_ENCODING,
                severity="INFO",
                text=(
                    f"The upload was read as {decoded.encoding} rather than UTF-8, "
                    "so one odd byte may show as '?'. Check names and dates against "
                    "the original file."
                ),
            )
        )
    for key in ("invoice_date", "delivery_date"):
        hit = hits.get(key)
        if hit is not None and hit.ambiguous_date_order:
            warnings.append(
                Warning(
                    code=WARN_DATE_ORDER,
                    severity="INFO",
                    text=(
                        f'"{hit.source_text}" was read as {hit.value} (DD/MM/YYYY, '
                        "the order Indian exports use). Both parts are 12 or less, "
                        "so the order cannot be told from the text - check it before "
                        "you confirm."
                    ),
                )
            )

    messages: list[ExtractedMessage] = []
    if kind == SourceKind.WHATSAPP_EXPORT:
        messages, chat_warnings = _chat(
            lines,
            field_delivery=hits.get("delivery_date"),
            window=objection_window_days,
            window_ref=window_source_ref,
            window_verified=window_verified,
        )
        warnings.extend(chat_warnings)

    if llm is not None:
        payload = suggest(
            llm, text=decoded.text, source_kind=kind.value, transport=llm_transport
        )
        if payload is None:
            warnings.append(
                Warning(
                    code=WARN_LLM_UNAVAILABLE,
                    severity="INFO",
                    text=(
                        "The optional language-model layer did not answer, so every "
                        "value here came from the regex path. Nothing was lost: the "
                        "regex result stands as it is."
                    ),
                )
            )
        else:
            filled = apply_llm(fields, payload)
            if filled:
                warnings.append(
                    Warning(
                        code=WARN_LLM_FILLED,
                        severity="INFO",
                        text=(
                            f"{filled} field(s) the regex path could not read were "
                            "filled by the language model (method: llm). They are "
                            "machine-suggested like everything else - confirm them."
                        ),
                    )
                )

    return ExtractionResponse(
        contract_version=CONTRACT_VERSION,
        kind=kind,
        fields=fields,
        supplier_name=supplier_name,
        messages=messages,
        confirm_schema=_confirm_entries(),
        cache_hit=False,
        warnings=warnings,
    )


def _field_objects(
    hits: dict[str, FieldHit], penalty: float
) -> dict[str, ExtractedField]:
    """All contract keys, filled from the hits or marked `missing`.

    `page` stays null on purpose: this pipeline reads text, and the citation is
    the line number (CR-4's `page` field is kept for shape compatibility).
    """
    objects: dict[str, ExtractedField] = {}
    for key in FIELD_KEYS:
        hit = hits.get(key)
        if hit is None:
            objects[key] = ExtractedField(
                value=None,
                source_text=None,
                page=None,
                line=None,
                method=ExtractionMethod.MISSING,
                confidence=0.0,
                machine_suggested=True,
            )
            continue
        objects[key] = ExtractedField(
            value=hit.value,
            source_text=hit.source_text,
            page=None,
            line=hit.line,
            method=ExtractionMethod.REGEX,
            confidence=round(max(0.0, hit.confidence - penalty), 2),
            machine_suggested=True,
        )
    return objects


def _chat(
    lines: tuple[str, ...],
    *,
    field_delivery: FieldHit | None,
    window: int | None,
    window_ref: str | None,
    window_verified: bool,
) -> tuple[list[ExtractedMessage], list[Warning]]:
    """Parse and tag an export. Lateness needs both an anchor and a window."""
    parsed = parse_messages(lines)
    warnings: list[Warning] = []

    # Two passes: lexical tags first (they include delivery), which finds the
    # anchor; then the same tags again with the anchor, so day counts and the
    # late-complaint tag are computed rather than assumed.
    anchor = delivery_anchor(tag_messages(parsed, anchor=None, window_days=None))
    if anchor is None and field_delivery is not None:
        try:
            anchor = date.fromisoformat(field_delivery.value)
        except ValueError:
            anchor = None

    if anchor is None:
        warnings.append(
            Warning(
                code=WARN_NO_ANCHOR,
                severity="WARN",
                text=(
                    "No delivery date could be read from this text, so days after "
                    "delivery and the late-complaint tag were not assessed. The "
                    "other tags still stand."
                ),
            )
        )
    if window is None:
        warnings.append(
            Warning(
                code=WARN_WINDOW_MISSING,
                severity="WARN",
                text=(
                    "The statute config has no objection window, so no complaint "
                    "could be tagged as late. This tagger holds no statutory number "
                    "of its own; the window is read from config by the caller."
                ),
            )
        )
    elif anchor is not None:
        verified_note = (
            "the config marks this value verified"
            if window_verified
            else "the config still marks this value unverified (OQ-1, source "
            f"{window_ref or 'unknown'})"
        )
        warnings.append(
            Warning(
                code=WARN_WINDOW_APPLIED,
                severity="INFO",
                text=(
                    f"Lateness was assessed against the configured objection window "
                    f"of {window} days from the delivery date, and {verified_note}. "
                    "A late tag is a suggestion: the engine re-derives the same "
                    "question from the confirmed request."
                ),
            )
        )

    tagged = tag_messages(parsed, anchor=anchor, window_days=window)
    messages = [
        ExtractedMessage.model_validate(message.to_dict()) for message in tagged
    ]
    if not any(message.tags for message in messages):
        warnings.append(
            Warning(
                code=WARN_NO_CANDIDATES,
                severity="INFO",
                text=(
                    "No candidate lines were recognised in this export. Nothing is "
                    "wrong with the file - the patterns simply found no delivery, "
                    "objection, resolution or payment line."
                ),
            )
        )
    ambiguous = ambiguous_header_dates(lines)
    if ambiguous:
        shown = ", ".join(str(n) for n in ambiguous[:5])
        more = "" if len(ambiguous) <= 5 else f" (+{len(ambiguous) - 5} more)"
        warnings.append(
            Warning(
                code=WARN_DATE_ORDER,
                severity="INFO",
                text=(
                    f"Chat dates on line(s) {shown}{more} could be read either way. "
                    "Header dates are read as DD/MM/YYYY (Indian export); check "
                    "those lines before confirming."
                ),
            )
        )
    return messages, warnings


def _confirm_entries() -> list[ConfirmEntry]:
    return [
        ConfirmEntry(
            key=spec.key,
            path=spec.path,
            kind=ConfirmKind(spec.kind.upper()),
            type=ConfirmFieldType(spec.type.upper()),
            required=spec.required,
            note=spec.note,
        )
        for spec in CONFIRM_SCHEMA
    ]
