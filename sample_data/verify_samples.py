#!/usr/bin/env python3
"""Check the sample corpus against its own ground truth.

What it proves
--------------
1. Every file in `MANIFEST.json` exists, and every generated file is listed
   (no orphan pages hiding outside the ground truth).
2. Every `.txt` twin and chat export, run through the **real** extraction
   pipeline, yields exactly the field values the manifest promises.
3. Chats produce the expected tags and day counts.
4. Digital PDFs carry a text layer with the key strings; scans and photos carry
   no text layer at all, so an OCR test really is an OCR test.

It does not judge the legal engine, and it deliberately does not "fix" a
mismatch: if a reading is wrong, the document or the extractor is wrong, not
the ground truth.

Run from the repository root:

    python sample_data/verify_samples.py
    python sample_data/verify_samples.py --verbose
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from backend.extraction.extract import extract_evidence  # noqa: E402

MANIFEST = HERE / "MANIFEST.json"
SKIP_NAMES = {"README.md", "MANIFEST.json", "generate_samples.py", "verify_samples.py"}
# A structurally valid GSTIN: 2 state digits, a 5-letter PAN prefix, 4 digits,
# a letter, an entity digit, "Z", and a checksum. The corpus uses 16-character
# "29SYN..." placeholders, so this must never match.
REAL_GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z]\d\b")
FIELD_KEYS = (
    "invoice_number",
    "invoice_date",
    "amount",
    "supplier_gstin",
    "buyer_gstin",
    "buyer_name",
    "delivery_date",
    "po_reference",
    "written_credit_days",
)


class Failure(Exception):
    pass


def _window() -> tuple[int | None, str | None, bool]:
    config = json.loads(
        (ROOT / "backend" / "config" / "statute_config.json").read_text(
            encoding="utf-8"
        )
    )
    entry = config["objection_window_days"]
    value = entry.get("value")
    return (
        int(value) if value is not None else None,
        entry.get("source_ref"),
        bool(entry.get("verified", False)),
    )


def _files_on_disk() -> set[str]:
    found = set()
    for path in HERE.rglob("*"):
        if not path.is_file():
            continue
        if path.name in SKIP_NAMES:
            continue
        found.add(path.relative_to(HERE).as_posix())
    return found


def _extract(path: Path):
    window, source_ref, verified = _window()
    return extract_evidence(
        raw=path.read_bytes(),
        objection_window_days=window,
        window_source_ref=source_ref,
        window_verified=verified,
    )


def _check_fields(entry: dict, response) -> None:
    for key, expected in entry["expected"].items():
        if key == "supplier_name":
            actual = response.supplier_name
        elif key in FIELD_KEYS:
            actual = response.fields[key].value
        else:
            raise Failure(f"unknown expected key {key!r} in {entry['file']}")
        if actual != expected:
            method = (
                "top-level"
                if key == "supplier_name"
                else response.fields[key].method.value
            )
            raise Failure(
                f"{key}: expected {expected!r}, extractor said {actual!r} "
                f"(method {method})"
            )


def _check_warnings(entry: dict, response) -> None:
    codes = {warning.code for warning in response.warnings}
    for wanted in entry.get("expected_warnings", []):
        if wanted not in codes:
            raise Failure(f"expected warning {wanted} missing; got {sorted(codes)}")
    for unwanted in entry.get("not_expected_warnings", []):
        if unwanted in codes:
            raise Failure(
                f"warning {unwanted} should not be present; got {sorted(codes)}"
            )


def _check_kind(entry: dict, response) -> None:
    wanted = entry.get("expect_kind")
    if wanted and response.kind.value != wanted:
        raise Failure(f"kind: expected {wanted}, got {response.kind.value}")


def _check_messages(entry: dict, response) -> None:
    for wanted in entry.get("expected_messages", []):
        snippet = wanted["contains"].lower()
        match = next((m for m in response.messages if snippet in m.text.lower()), None)
        if match is None:
            raise Failure(f"no extracted message containing {wanted['contains']!r}")
        tags = sorted(tag.value for tag in match.tags)
        expected_tags = sorted(wanted.get("tags", []))
        if tags != expected_tags:
            raise Failure(
                f"message {wanted['contains']!r}: expected tags {expected_tags}, got {tags}"
            )
        if "days_after_delivery" in wanted:
            if match.days_after_delivery != wanted["days_after_delivery"]:
                raise Failure(
                    f"message {wanted['contains']!r}: expected day "
                    f"{wanted['days_after_delivery']}, got {match.days_after_delivery}"
                )
        if "within_objection_window" in wanted:
            if match.within_objection_window != wanted["within_objection_window"]:
                raise Failure(
                    f"message {wanted['contains']!r}: expected within_window "
                    f"{wanted['within_objection_window']}, got "
                    f"{match.within_objection_window}"
                )


def _check_pdf(entry: dict, path: Path) -> None:
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - developer message
        raise Failure("PyMuPDF is not installed; cannot check the PDF layer")

    doc = pymupdf.open(str(path))
    try:
        text = "\n".join(page.get_text() for page in doc)
        if entry.get("text_layer") is True:
            if not text.strip():
                raise Failure("digital PDF has no extractable text layer")
            for needle in entry.get("text_layer_must_contain", []):
                if needle not in text:
                    raise Failure(f"text layer is missing {needle!r}")
        elif entry.get("text_layer") is False and entry["role"] != "chat_render":
            if text.strip():
                raise Failure(
                    "this file is meant to be an image-only OCR target, but it "
                    f"carries a text layer ({text.strip()[:60]!r})"
                )
        if entry.get("pages") is not None and doc.page_count != entry["pages"]:
            raise Failure(
                f"page count: manifest says {entry['pages']}, file has {doc.page_count}"
            )
    finally:
        doc.close()


def run(verbose: bool) -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = manifest["files"]
    listed = {entry["file"] for entry in entries}
    on_disk = _files_on_disk()

    problems: list[str] = []
    checked = 0

    for missing in sorted(listed - on_disk):
        problems.append(f"{missing}: listed in MANIFEST.json but not on disk")
    for orphan in sorted(on_disk - listed):
        problems.append(f"{orphan}: on disk but not in MANIFEST.json")

    for path in sorted(HERE.rglob("*")):
        if path.suffix.lower() not in (".txt", ".eml", ".md") or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in REAL_GSTIN.finditer(text):
            problems.append(
                f"{path.relative_to(HERE).as_posix()}: {match.group(0)} is shaped "
                "like a real GSTIN; the corpus must use placeholder numbers only"
            )

    for entry in entries:
        path = HERE / entry["file"]
        if not path.is_file():
            continue
        try:
            if entry["role"] in ("text_twin", "chat_export"):
                response = _extract(path)
                _check_fields(entry, response)
                _check_kind(entry, response)
                _check_warnings(entry, response)
                _check_messages(entry, response)
                checked += 1
            elif path.suffix.lower() in (".pdf", ".png"):
                _check_pdf(entry, path)
                checked += 1
            if verbose:
                print(f"ok   {entry['file']}")
        except Failure as exc:
            problems.append(f"{entry['file']}: {exc}")

    print()
    if problems:
        print(f"FAILED: {len(problems)} problem(s)\n")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(f"OK: {checked} checks passed across {len(entries)} manifest entries.")
    print(f"    {len(entries)} files, ground truth in {MANIFEST.name}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    return run(args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
