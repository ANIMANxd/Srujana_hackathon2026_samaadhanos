"""Bytes to text, offline: encoding detection, size guard, binary refusal.

WhatsApp exports and pasted invoice text arrive as bytes with no reliable
charset, so this module tries the shapes that actually occur (UTF-16 with a BOM
from an old Notepad, UTF-8, then cp1252 for Windows exports) and reports which
one it used, so the route can say so instead of hiding it.

It raises `ExtractionInputError` with a plain-English message; the route maps
that to 400 with the contract's error envelope.
"""

from dataclasses import dataclass

# Two megabytes of text is far beyond any chat or invoice the demo handles, and
# the guard keeps one huge paste from becoming the whole request.
MAX_BYTES = 2 * 1024 * 1024

UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")
BINARY_PREFIXES = (b"%PDF", b"PK\x03\x04", b"\x89PNG", b"GIF8", b"\x1f\x8b")


class ExtractionInputError(ValueError):
    """An upload extraction cannot read. Plain English, no stack trace."""


@dataclass(frozen=True)
class DecodedText:
    text: str
    encoding: str
    lines: tuple[str, ...]

    @property
    def encoding_was_guessy(self) -> bool:
        """True when the bytes were not clean UTF-8, worth a note in the response."""
        return self.encoding not in ("utf-8", "utf-8-sig")


def decode_text(raw: bytes) -> DecodedText:
    """Decode an upload to text, or explain why it cannot be read."""
    if not raw:
        raise ExtractionInputError("The file is empty, so there is nothing to read.")
    if len(raw) > MAX_BYTES:
        raise ExtractionInputError(
            f"The file is {len(raw)} bytes, over the {MAX_BYTES} byte limit for "
            "extraction. Upload the text itself - a .txt export or the invoice text."
        )

    if raw.startswith(UTF16_BOMS):
        text, encoding = raw.decode("utf-16"), "utf-16"
    elif raw.startswith(BINARY_PREFIXES) or _looks_binary(raw):
        raise ExtractionInputError(
            "That looks like a binary file (a PDF or an image), and extraction only "
            "reads plain text. Upload a .txt export or paste the invoice or PO text."
        )
    else:
        text, encoding = _decode_textual(raw)

    if not text.strip():
        raise ExtractionInputError(
            "The file decoded but has no readable text in it. Check it is a text export."
        )
    return DecodedText(text=text, encoding=encoding, lines=tuple(text.splitlines()))


def _decode_textual(raw: bytes) -> tuple[str, str]:
    """UTF-8 first (the common case), cp1252 as the Windows fallback."""
    try:
        return raw.decode("utf-8-sig"), "utf-8-sig"
    except UnicodeDecodeError:
        # cp1252 leaves five byte values undefined; replace rather than crash so
        # one odd byte cannot refuse an otherwise readable file.
        return raw.decode("cp1252", errors="replace"), "cp1252"


def _looks_binary(raw: bytes) -> bool:
    """NUL-heavy or mostly non-text bytes: a PDF body, a zip, an image."""
    sample = raw[:4096]
    if b"\x00" in sample:
        return True
    printable = sum(1 for b in sample if 32 <= b < 127 or b in (9, 10, 13))
    return printable / len(sample) < 0.75
