"""Extraction tests (architecture.md section 11, `tests/contract`).

What they prove, per task B9's acceptance:

- the **regex path works offline** - a socket during a default run is an error;
- the synthetic chat yields a **day-9 defect objection** and a **day-24 late
  complaint**, both with their line numbers, both marked machine-suggested;
- invoice and PO text yields the contract's field keys with line citations;
- the confirm schema's paths really resolve against `CaseEvaluationRequest`;
- the LLM layer is optional, behind its flag, fills only what regex missed, and
  a dead endpoint changes nothing;
- the demo cache returns a prepared result, and the committed cache is exactly
  what the code produces now (freshness, like the fixtures);
- the engine never imports this package.

Nothing here asserts a legal value: dates and counts in the chat are the file's
own, and the objection window is the config's.
"""

import json
import urllib.request
from pathlib import Path
from typing import get_args, get_origin

from fastapi.testclient import TestClient

from backend.app.config_loader import load_config, objection_window
from backend.app.main import app
from backend.app.schemas import (
    ArtifactKind,
    CaseEvaluationRequest,
    ExtractionMethod,
    ExtractionResponse,
)
from backend.extraction import cache
from backend.extraction.extract import (
    WARN_CACHE_HIT,
    WARN_LLM_FILLED,
    WARN_LLM_UNAVAILABLE,
    WARN_WINDOW_APPLIED,
    WARN_WINDOW_MISSING,
    extract_evidence,
)
from backend.extraction.llm import settings_from_env
from backend.extraction.tags import FIELD_KEYS, MessageTag

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "backend" / "extraction" / "demo"
CHAT = DEMO / "chat_defect_day9.txt"
INVOICE = DEMO / "invoice_synthetic.txt"
PO = DEMO / "po_synthetic.txt"

# The eight keys the frontend already mirrors (CR-4) plus the credit-day key.
MIRRORED_KEYS = {
    "invoice_number",
    "invoice_date",
    "amount",
    "supplier_gstin",
    "buyer_gstin",
    "buyer_name",
    "delivery_date",
    "po_reference",
}

client = TestClient(app)


# ------------------------------------------------------------- helpers ----


def _upload(path: Path, filename: str | None = None) -> ExtractionResponse:
    response = client.post(
        "/api/v1/extract-evidence",
        files={"file": (filename or path.name, path.read_bytes(), "text/plain")},
    )
    assert response.status_code == 200, response.text[:600]
    return ExtractionResponse.model_validate(response.json())


def _chat_lines() -> list[str]:
    return CHAT.read_text(encoding="utf-8").splitlines()


def _line_containing(needle: str, path: Path = CHAT) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    return next(i for i, line in enumerate(lines, start=1) if needle in line)


def _message(response: ExtractionResponse, line: int):
    matches = [m for m in response.messages if m.line == line]
    assert matches, f"no parsed message on line {line}"
    return matches[0]


def _resolve_path(path: str) -> bool:
    """Walk a confirm-schema path against the real contract models.

    Each segment must be a real field name of the model reached so far; list
    brackets are index selectors (`items[INVOICE]`) or list markers
    (`objections[]`), so they are stripped. The last segment may be a scalar.
    """
    model = CaseEvaluationRequest
    names = [segment.partition("[")[0] for segment in path.split(".")]
    for position, name in enumerate(names):
        if not name:
            continue  # `objections[]` ends with an empty segment: the list itself
        if name not in getattr(model, "model_fields", {}):
            return False
        if position == len(names) - 1:
            return True
        annotation = model.model_fields[name].annotation
        if get_origin(annotation) is list:
            annotation = get_args(annotation)[0]
        if not hasattr(annotation, "model_fields"):
            return False
        model = annotation
    return True


# ------------------------------------------------- the synthetic chat ----


def test_chat_tags_a_day9_defect_objection():
    """Acceptance: day 9 is a defect objection, inside the window, cited."""
    response = _upload(CHAT)
    assert response.kind == "WHATSAPP_EXPORT"
    message = _message(response, _line_containing("Day 9"))
    assert MessageTag.DEFECT_OBJECTION in message.tags
    assert MessageTag.LATE_COMPLAINT not in message.tags
    assert message.days_after_delivery == 9
    assert message.within_objection_window is True
    assert message.sent is not None and message.sent.isoformat() == "2026-02-12"
    assert message.machine_suggested is True
    assert 0.0 < message.confidence <= 1.0
    assert message.text


def test_chat_tags_a_day24_late_complaint():
    """Acceptance: day 24 is late - after the window from the delivery line."""
    response = _upload(CHAT)
    message = _message(response, _line_containing("Day 24"))
    assert MessageTag.LATE_COMPLAINT in message.tags
    assert MessageTag.DEFECT_OBJECTION in message.tags
    assert message.days_after_delivery == 24
    assert message.within_objection_window is False
    assert message.sent is not None and message.sent.isoformat() == "2026-02-27"
    assert message.machine_suggested is True


def test_chat_line_numbers_are_the_real_file_lines():
    """Citations point at the file, so a human can open it and look."""
    response = _upload(CHAT)
    parsed = {m.line for m in response.messages}
    assert _line_containing("We received the 40 boxes") in parsed
    assert _line_containing("Payment for the invoice") in parsed
    for message in response.messages:
        assert message.line >= 4, "the file's two prose lines are not messages"
        assert 1 <= message.line <= len(_chat_lines())


def test_chat_covers_all_five_tags():
    response = _upload(CHAT)
    seen = {tag for message in response.messages for tag in message.tags}
    assert seen == set(MessageTag)


def test_chat_reports_whether_the_window_was_assessed():
    """Lateness needs the configured window; either way the response says so."""
    response = _upload(CHAT)
    codes = {w.code for w in response.warnings}
    assert codes & {WARN_WINDOW_APPLIED, WARN_WINDOW_MISSING}


def test_chat_without_a_window_never_claims_lateness():
    """No config window -> the tag is simply withheld, not guessed."""
    response = extract_evidence(raw=CHAT.read_bytes(), objection_window_days=None)
    assert WARN_WINDOW_MISSING in {w.code for w in response.warnings}
    for message in response.messages:
        assert MessageTag.LATE_COMPLAINT not in message.tags
        assert message.within_objection_window is None


def test_chat_field_values_are_penalised_but_still_cited():
    """A value read from a conversation shows a lower confidence than the same
    value read off the invoice, and keeps its line."""
    response = _upload(CHAT)
    field = response.fields["invoice_number"]
    assert field.value == "SYN-INV-0042"
    assert field.line == _line_containing("Dispatched 40 boxes")
    assert field.method == ExtractionMethod.REGEX
    assert field.confidence <= 0.85  # 0.85 - the chat penalty
    assert field.machine_suggested is True


# -------------------------------------------------- document extraction ----


def test_invoice_fields_all_cite_a_line():
    response = _upload(INVOICE)
    assert response.kind == "DOCUMENT_TEXT"
    assert response.supplier_name is not None
    for key in MIRRORED_KEYS:
        field = response.fields[key]
        assert field.line is not None, f"{key} has no line citation"
        assert field.source_text, f"{key} has no source line"
        assert field.method == ExtractionMethod.REGEX
        assert 0.0 < field.confidence <= 1.0
        assert field.machine_suggested is True
        assert field.page is None, "text uploads have no pages; line is the citation"
    assert response.fields["invoice_date"].value == "2026-01-12"
    assert response.fields["delivery_date"].value == "2026-01-16"
    assert response.fields["amount"].value == "315000.00"  # Decimal string, no float
    assert response.fields["supplier_gstin"].value == "29SYN000000001Z1"
    assert response.fields["buyer_gstin"].value == "29SYN000000000Z1"


def test_missing_fields_report_missing_not_a_guess():
    response = _upload(PO)
    for key in MIRRORED_KEYS:
        assert key in response.fields, "every contract key is present, filled or not"
    absent = response.fields["amount"]
    assert absent.value is None
    assert absent.method == ExtractionMethod.MISSING
    assert absent.confidence == 0.0
    assert absent.line is None


def test_po_credit_days_phrase_is_extracted():
    response = _upload(PO)
    credit = response.fields["written_credit_days"]
    assert credit.value == "30"
    assert credit.line == _line_containing("Net 30 days", PO)
    assert "Net 30 days" in (credit.source_text or "")


def test_invoice_date_never_takes_a_delivery_or_order_label():
    """`Order date:` and `Delivery:` are neither the invoice date nor swapped."""
    invoice = _upload(INVOICE)
    assert invoice.fields["invoice_date"].line == _line_containing(
        "Date: 12/01/2026", INVOICE
    )
    po = _upload(PO)
    assert po.fields["invoice_date"].value is None
    assert po.fields["delivery_date"].value == "2026-03-04"


def test_ambiguous_date_order_is_flagged():
    response = _upload(INVOICE)
    warnings = [w for w in response.warnings if w.code == "DATE_ORDER_ASSUMED"]
    assert warnings, "12/01/2026 could be either order and must be flagged"
    assert "DD/MM/YYYY" in warnings[0].text


# ------------------------------------------------------- confirm schema ----


def test_confirm_schema_covers_every_candidate_and_resolves():
    response = _upload(INVOICE)
    entries = {entry.key: entry for entry in response.confirm_schema}
    expected = set(FIELD_KEYS) | {"supplier_name"} | {t.value for t in MessageTag}
    assert set(entries) == expected
    for entry in response.confirm_schema:
        if entry.path is None:
            assert entry.note, "an unmappable field must say where it goes instead"
            continue
        assert _resolve_path(entry.path), f"{entry.key} points at nothing: {entry.path}"
    # The mapping is literally a CaseEvaluationRequest path, contract field names.
    assert entries["amount"].path == "transaction.principal"
    assert entries["invoice_date"].path == "transaction.invoice_date"
    assert entries["buyer_name"].path == "buyer.name"
    assert entries[MessageTag.DEFECT_OBJECTION.value].path == "objections[]"
    assert entries[MessageTag.PAYMENT_PROMISE.value].path == "acknowledgments[]"
    assert entries[MessageTag.RESOLUTION_ACK.value].path == "objections[].resolved_date"


def test_response_shape_matches_the_frontend_mirror():
    """CR-4's `{fields, supplier_name}` plus the additions, keys and all."""
    response = _upload(INVOICE)
    assert set(response.fields) == set(FIELD_KEYS)
    assert set(FIELD_KEYS) >= MIRRORED_KEYS
    assert response.contract_version == "1.0"
    assert response.cache_hit is False
    assert any(w.code == "MACHINE_SUGGESTED" for w in response.warnings)
    # Nothing that belongs to an evaluation leaks into an extraction payload.
    payload = response.model_dump(mode="json")
    assert not (
        {"jurisdiction", "financials", "buyer_cost", "total_claim"} & set(payload)
    )


# ------------------------------------------------------- engine boundary ----


def test_engine_never_imports_extraction():
    """Constraint: the legal engine never calls this module."""
    offenders = [
        path.name
        for path in sorted((ROOT / "backend" / "engine").glob("*.py"))
        if "backend.extraction" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"engine modules importing extraction: {offenders}"


def test_artifacts_do_not_import_extraction():
    offenders = [
        path.name
        for path in sorted((ROOT / "backend" / "artifacts").glob("*.py"))
        if "backend.extraction" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


# ------------------------------------------------------------- offline ----


def test_default_path_never_touches_the_network(monkeypatch):
    """Acceptance: the regex path works offline. A socket would fail loudly."""
    calls: list[str] = []

    def banned(url=None, *args, **kwargs):
        calls.append(str(url))
        raise AssertionError("extraction opened a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", banned)
    assert _upload(INVOICE).fields["amount"].value
    assert _upload(CHAT).messages
    assert calls == [], "the LLM layer ran without its flag"


def test_llm_flags_are_off_by_default():
    assert settings_from_env({}) is None
    assert settings_from_env({"EXTRACTION_LLM": "1"}) is None  # flag without URL
    assert (
        settings_from_env({"EXTRACTION_LLM": "0", "EXTRACTION_LLM_URL": "http://x"})
        is None
    )
    settings = settings_from_env(
        {"EXTRACTION_LLM": "1", "EXTRACTION_LLM_URL": "http://x"}
    )
    assert settings is not None and settings.url == "http://x"


def test_llm_fills_only_what_regex_missed():
    """The deterministic path stays authoritative: a regex hit is never replaced."""
    seen: dict[str, str] = {}

    def transport(settings, payload):
        seen["kind"] = payload["kind"]
        return {
            "fields": {
                # missing in the PO -> filled; present in the PO -> ignored
                "amount": {"value": "600000.00", "confidence": 0.8},
                "po_reference": {"value": "SHOULD-NOT-APPEAR", "confidence": 0.99},
            }
        }

    response = extract_evidence(
        raw=PO.read_bytes(),
        llm=settings_from_env(
            {"EXTRACTION_LLM": "1", "EXTRACTION_LLM_URL": "http://llm.test"}
        ),
        llm_transport=transport,
    )
    assert seen["kind"] == "DOCUMENT_TEXT"
    assert response.fields["amount"].value == "600000.00"
    assert response.fields["amount"].method == ExtractionMethod.LLM
    assert response.fields["po_reference"].value == "SYN-PO-0077"
    assert response.fields["po_reference"].method == ExtractionMethod.REGEX
    assert WARN_LLM_FILLED in {w.code for w in response.warnings}
    # still machine-suggested, whatever produced it
    assert response.fields["amount"].machine_suggested is True


def test_llm_failure_changes_nothing():
    def transport(settings, payload):
        return None  # a dead endpoint, a timeout, a 500 - all the same

    before = extract_evidence(raw=INVOICE.read_bytes())
    after = extract_evidence(
        raw=INVOICE.read_bytes(),
        llm=settings_from_env(
            {"EXTRACTION_LLM": "1", "EXTRACTION_LLM_URL": "http://llm.test"}
        ),
        llm_transport=transport,
    )
    assert before.fields == after.fields
    assert WARN_LLM_UNAVAILABLE in {w.code for w in after.warnings}


def test_route_reads_the_llm_flag_without_calling_home(monkeypatch):
    """The route honours the flag, and a failing endpoint still returns 200."""
    monkeypatch.setenv("EXTRACTION_LLM", "1")
    monkeypatch.setenv("EXTRACTION_LLM_URL", "http://llm.test")
    monkeypatch.setattr(
        "backend.extraction.llm.post_json", lambda settings, payload: None
    )
    response = client.post(
        "/api/v1/extract-evidence",
        files={"file": ("inv.txt", INVOICE.read_bytes(), "text/plain")},
    )
    assert response.status_code == 200
    assert WARN_LLM_UNAVAILABLE in {w["code"] for w in response.json()["warnings"]}


# ---------------------------------------------------------- demo cache ----


def test_demo_cache_returns_the_prepared_result(monkeypatch):
    monkeypatch.setenv("EXTRACTION_DEMO_CACHE", "1")
    response = _upload(INVOICE)
    assert response.cache_hit is True
    assert WARN_CACHE_HIT in {w.code for w in response.warnings}
    assert response.fields["amount"].value == "315000.00"


def test_committed_cache_is_exactly_what_the_code_produces():
    """Freshness, like the fixtures: a stale cache fails this test."""
    window, window_ref, window_verified = objection_window(load_config())
    for path in sorted(DEMO.glob("*.txt")):
        raw = path.read_bytes()
        stored = cache.load(raw.decode("utf-8"))
        assert stored is not None, f"no cache entry for {path.name}"
        fresh = extract_evidence(
            raw=raw,
            objection_window_days=window,
            window_source_ref=window_ref,
            window_verified=window_verified,
        ).model_dump(mode="json")
        assert stored == fresh, f"{path.name} cache drifted; run cache_build"


# -------------------------------------------------------------- errors ----


def test_empty_file_is_a_plain_400():
    response = client.post(
        "/api/v1/extract-evidence", files={"file": ("x.txt", b"", "text/plain")}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "RULE_VIOLATION"


def test_binary_upload_is_refused_with_advice():
    response = client.post(
        "/api/v1/extract-evidence",
        files={"file": ("x.pdf", b"%PDF-1.4 ...", "application/pdf")},
    )
    assert response.status_code == 400
    assert "plain text" in response.json()["error"]["message"]


def test_missing_file_is_a_422_with_the_envelope():
    response = client.post("/api/v1/extract-evidence", json={"nope": True})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_extraction_is_deterministic():
    first = _upload(CHAT)
    second = _upload(CHAT)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_artifact_kinds_still_unaffected_by_the_new_route():
    """The two POST routes are independent: adding one did not disturb the other."""
    request = json.loads(
        (ROOT / "backend" / "presets" / "case_01.json").read_text(encoding="utf-8")
    )["request"]
    response = client.post(
        "/api/v1/generate-artifact",
        json={"kind": ArtifactKind.STAGE1_ACCEPTANCE_NOTE.value, "request": request},
    )
    assert response.status_code == 200
