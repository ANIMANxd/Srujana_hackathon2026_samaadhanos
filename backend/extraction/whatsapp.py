"""WhatsApp export parser and candidate tagger - regex and keywords first.

Reads the two export shapes WhatsApp actually writes (Android and iOS), joins
wrapped continuation lines onto the message they belong to, and tags each
message from what it says plus where it sits in time.

Tagging rules, stated plainly because every one of them is a *suggestion*:

- `DELIVERY_CONFIRMATION`, `DEFECT_OBJECTION`, `RESOLUTION_ACK`,
  `PAYMENT_PROMISE` come from keyword patterns on the message text. They say
  what a line reads like, never what the law makes of it.
- `LATE_COMPLAINT` is the only temporal tag: a concern message whose date falls
  **after** the delivery anchor plus the objection window. The window is passed
  in by the route from statute config - this module holds no statutory number
  of its own (golden rule 4) - and when the anchor or the window is missing the
  tag is simply not applied and the response says so.

Dates are read as DD/MM/YYYY, the order Indian exports use (stated as an
assumption in the response, because 03/04/2026 is genuinely ambiguous).
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

from backend.extraction.tags import MessageTag

# Longest chat line we carry into the response; the rest stays in the file.
MAX_TEXT = 400

# --------------------------------------------------------------- parsing ----

# Android: 12/02/2026, 9:15 PM - Ravi: message  (comma and seconds optional)
_ANDROID_HEADER = re.compile(
    r"^(?P<date>\d{1,2}/\d{1,2}/\d{2,4}),\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AaPp][Mm])?)\s*"
    r"-\s+(?P<sender>[^:]{1,80}):\s?(?P<text>.*)$",
    re.IGNORECASE,
)

# iOS: [12/02/2026, 9:15:12 PM] Ravi: message
_IOS_HEADER = re.compile(
    r"^\[(?P<date>\d{1,2}/\d{1,2}/\d{2,4}),\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AaPp][Mm])?)\]\s*"
    r"(?P<sender>[^:]{1,80}):\s?(?P<text>.*)$",
    re.IGNORECASE,
)

# ------------------------------------------------------------ tag patterns ----
# Each tuple is checked in order and every match applies; a message can carry
# several tags (a late defect complaint carries two).

DELIVERY_PATTERNS: tuple[str, ...] = (
    r"\bwe (have )?received\b",
    r"\breceived (the |our |this |your )?(goods|stock|boxes|cartons|consignment|"
    r"shipment|material|delivery|order)\b",
    r"\bdelivery (was )?(done|completed|confirmed|received|accepted)\b",
    r"\bgoods (have been )?received\b",
    r"\bgrn (raised|signed|ok|done|created)\b",
    r"\bsigned the (lr|challan|delivery receipt)\b",
    r"\bchallan (accepted|signed|received)\b",
)

DEFECT_PATTERNS: tuple[str, ...] = (
    r"\bdefect(ive|s)?\b",
    r"\bdamag(ed|e|ing)\b",
    r"\bbroken\b",
    r"\bcracked\b",
    r"\bleaking\b",
    r"\bshort (supply|shipment|delivered|by)\b",
    r"\bwrong (item|size|quantity|qty|product|material)\b",
    r"\bquality (issue|problem|complaint|concern)\b",
    r"\bnot as per (spec|specification|sample|po)\b",
    r"\breject(ed|ing)\b",
    r"\bscrap(ped)?\b",
    r"\bmissing (parts|units|boxes|items|pieces)\b",
)

# Anything that reads as a concern, defect or not - the set LATE_COMPLAINT is
# measured over, so a plain "this is unacceptable" counts too.
CONCERN_PATTERNS: tuple[str, ...] = DEFECT_PATTERNS + (
    r"\bcomplain(t|s|ed|ing)\b",
    r"\b(unacceptable|unhappy|not happy)\b",
    r"\bstill (waiting|not resolved|unresolved)\b",
    r"\bconcern(s|ed)?\b",
)

RESOLUTION_PATTERNS: tuple[str, ...] = (
    r"\bresolved\b",
    r"\bresolution\b",
    r"\breplaced\b",
    r"\breplacement\b.*\b(sent|dispatched|done|arrived|received|confirmed)\b",
    r"\bcredit note\b",
    r"\bissue (is |has been )?(closed|fixed|sorted|resolved)\b",
    r"\bfixed\b",
    r"\bthanks for (the )?(fixing|replacement|quick (fix|response|action))\b",
    r"\bwe (have )?issued the (credit|replacement)\b",
)

PROMISE_PATTERNS: tuple[str, ...] = (
    r"\bpayment\b.*\bwill be (released|made|done|initiated|paid|credited)\b",
    r"\bwill be (released|paid|cleared|credited) by\b",
    r"\breleasing (the |this )?payment\b",
    r"\bpay(ing)? (the |this |your )?(invoice|amount|due|balance)\b",
    r"\b(invoice|amount|payment|balance) (will|shall) be (paid|cleared|released)\b",
    r"\b(neft|rtgs|imps) (will be |to be )?(sent|initiated|done)\b",
    r"\bby (tomorrow|friday|monday|next week|week ?end|month end)\b.*\b"
    r"(pay|release|clear|credit)\b",
)

# How sure the tagger is that a line reads as its tag. These are extraction
# heuristics for the confidence column, not legal values, and every message
# stays machine-suggested whatever it is.
TAG_CONFIDENCE: dict[MessageTag, float] = {
    MessageTag.DELIVERY_CONFIRMATION: 0.85,
    MessageTag.DEFECT_OBJECTION: 0.9,
    MessageTag.RESOLUTION_ACK: 0.85,
    MessageTag.PAYMENT_PROMISE: 0.8,
    MessageTag.LATE_COMPLAINT: 0.9,
}

# Tag order in the response: the declaration order of the enum.
_TAG_ORDER = {tag: index for index, tag in enumerate(MessageTag)}

COMPILED = {
    MessageTag.DELIVERY_CONFIRMATION: tuple(
        re.compile(p, re.IGNORECASE) for p in DELIVERY_PATTERNS
    ),
    MessageTag.DEFECT_OBJECTION: tuple(
        re.compile(p, re.IGNORECASE) for p in DEFECT_PATTERNS
    ),
    MessageTag.RESOLUTION_ACK: tuple(
        re.compile(p, re.IGNORECASE) for p in RESOLUTION_PATTERNS
    ),
    MessageTag.PAYMENT_PROMISE: tuple(
        re.compile(p, re.IGNORECASE) for p in PROMISE_PATTERNS
    ),
}
_CONCERN = tuple(re.compile(p, re.IGNORECASE) for p in CONCERN_PATTERNS)


@dataclass(frozen=True)
class ChatMessage:
    """One parsed export line group. `line` is where the message starts."""

    line: int
    sender: str
    sent: date | None
    text: str

    @property
    def is_concern(self) -> bool:
        return any(p.search(self.text) for p in _CONCERN)


@dataclass(frozen=True)
class TaggedMessage:
    """A message with its candidate tags and its place in the timeline."""

    line: int
    sender: str
    sent: date | None
    text: str
    tags: tuple[MessageTag, ...]
    days_after_delivery: int | None
    within_objection_window: bool | None
    confidence: float

    def to_dict(self) -> dict:
        return {
            "line": self.line,
            "sender": self.sender,
            "sent": self.sent,
            "text": self.text,
            "tags": list(self.tags),
            "days_after_delivery": self.days_after_delivery,
            "within_objection_window": self.within_objection_window,
            "confidence": self.confidence,
            "machine_suggested": True,
        }


def looks_like_whatsapp(lines: tuple[str, ...] | list[str]) -> bool:
    """Any WhatsApp-shaped header line means this is an export, not a document."""
    return any(_header(line) for line in lines)


def _header(line: str):
    stripped = line.rstrip("\r")
    return _ANDROID_HEADER.match(stripped) or _IOS_HEADER.match(stripped)


def parse_messages(lines: tuple[str, ...] | list[str]) -> list[ChatMessage]:
    """Parse an export into messages; unwrapped continuation lines are joined."""
    messages: list[ChatMessage] = []
    for index, raw_line in enumerate(lines, start=1):
        match = _header(raw_line)
        if match:
            messages.append(
                ChatMessage(
                    line=index,
                    sender=match.group("sender").strip(),
                    sent=_parse_date(match.group("date")),
                    text=match.group("text").strip(),
                )
            )
        elif messages and raw_line.strip():
            # WhatsApp wraps long messages without repeating the header.
            previous = messages[-1]
            messages[-1] = ChatMessage(
                line=previous.line,
                sender=previous.sender,
                sent=previous.sent,
                text=_join(previous.text, raw_line.strip()),
            )
    return messages


def _join(existing: str, continuation: str) -> str:
    joined = f"{existing} {continuation}"
    return joined if len(joined) <= MAX_TEXT else joined[: MAX_TEXT - 3] + "..."


def _parse_date(value: str) -> date | None:
    """DD/MM/YYYY (Indian exports); a 2-digit year is read as 20xx."""
    parts = value.split("/")
    if len(parts) != 3:
        return None
    day, month, year = (int(p) for p in parts)
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


# --------------------------------------------------------------- tagging ----


def tag_messages(
    messages: list[ChatMessage],
    *,
    anchor: date | None,
    window_days: int | None,
) -> list[TaggedMessage]:
    """Tag every message. Lateness is only claimed when anchor and window exist."""
    tagged: list[TaggedMessage] = []
    for message in messages:
        tags = [
            tag
            for tag, patterns in COMPILED.items()
            if any(pattern.search(message.text) for pattern in patterns)
        ]
        days = (
            (message.sent - anchor).days
            if anchor is not None and message.sent is not None
            else None
        )
        within: bool | None = None
        if anchor is not None and window_days is not None and message.sent is not None:
            window_end = anchor + timedelta(days=window_days)
            within = message.sent <= window_end
            if within is False and message.is_concern:
                tags.append(MessageTag.LATE_COMPLAINT)
        if tags:
            tags.sort(key=_TAG_ORDER.__getitem__)
        tagged.append(
            TaggedMessage(
                line=message.line,
                sender=message.sender,
                sent=message.sent,
                text=(
                    message.text
                    if len(message.text) <= MAX_TEXT
                    else message.text[: MAX_TEXT - 3] + "..."
                ),
                tags=tuple(tags),
                days_after_delivery=days,
                within_objection_window=within,
                confidence=max((TAG_CONFIDENCE[t] for t in tags), default=0.0),
            )
        )
    return tagged


def delivery_anchor(tagged: list[TaggedMessage]) -> date | None:
    """The earliest delivery-confirmed date in the chat, used as day 0."""
    dates = [
        m.sent for m in tagged if MessageTag.DELIVERY_CONFIRMATION in m.tags and m.sent
    ]
    return min(dates) if dates else None


_HEADER_DATE = re.compile(
    r"^\[?(?P<day>\d{1,2})/(?P<month>\d{1,2})/(?P<year>\d{2,4})[,\]]"
)


def ambiguous_header_dates(lines: tuple[str, ...] | list[str]) -> list[int]:
    """Lines whose header date could honestly be read either way.

    `03/02/2026` is 3 February in an Indian export and 3 February in nobody
    else's; `05/03/2026` and `03/05/2026` are the ones where the order cannot
    be told. These are the dates the response should ask a human to check.
    """
    ambiguous: list[int] = []
    for index, line in enumerate(lines, start=1):
        match = _HEADER_DATE.match(line.strip())
        if not match:
            continue
        day, month = int(match.group("day")), int(match.group("month"))
        if day <= 12 and month <= 12 and day != month:
            ambiguous.append(index)
    return ambiguous


def count_tagged(tagged: list[TaggedMessage]) -> int:
    return sum(1 for message in tagged if message.tags)
