import re
from datetime import datetime, timezone
from html import unescape

from app.models import ParsedXymonAlert

FIELD_PATTERNS = {
    "host": [
        r"Host(?:name)?:\s*(.+)",
        r"Machine(?:\s+name)?:\s*(.+)",
        r"Device(?:\s+name)?:\s*(.+)",
    ],
    "test_name": [
        r"Test(?:\s+name)?:\s*(.+)",
        r"Service:\s*(.+)",
        r"Check:\s*(.+)",
    ],
    "status": [
        r"Status:\s*(red|yellow|purple|green|clear|critical|warning|ok)",
        r"Color:\s*(red|yellow|purple|green|clear)",
    ],
    "age": [
        r"Age:\s*(.+)",
        r"Duration:\s*(.+)",
    ],
    "group_name": [
        r"Group:\s*(.+)",
        r"Page:\s*(.+)",
    ],
    "message": [
        r"Message:\s*(.+)",
        r"Summary:\s*(.+)",
    ],
}

STATUS_WORDS = ("red", "yellow", "purple", "green", "clear", "critical", "warning", "ok")


def _clean_body(body: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", body, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _extract(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip().strip(".,;")
    return ""


def _parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    value = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(timezone.utc)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _normalize_status(raw: str, subject: str, text: str) -> str:
    combined = f"{raw} {subject} {text[:300]}".lower()
    if "critical" in combined:
        return "Red"
    if "warning" in combined:
        return "Yellow"
    if "clear" in combined or re.search(r"\bok\b", combined):
        return "Green"
    for word in STATUS_WORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", combined):
            return {"clear": "Green", "ok": "Green"}.get(word, word.capitalize())
    return raw.capitalize() if raw else ""


def parse_xymon_message(message: dict) -> ParsedXymonAlert:
    body = message.get("body", {}).get("content", "") or ""
    text = _clean_body(body)
    subject = message.get("subject", "") or ""
    sender = (
        message.get("from", {})
        .get("emailAddress", {})
        .get("address", "")
    )
    alert = ParsedXymonAlert(
        message_id=message.get("id", ""),
        internet_message_id=message.get("internetMessageId", ""),
        received_time=_parse_time(message.get("receivedDateTime")),
        subject=subject,
        sender=sender,
        raw_payload=text,
    )
    for field, patterns in FIELD_PATTERNS.items():
        setattr(alert, field, _extract(patterns, text))
    alert.status = _normalize_status(alert.status, subject, text)
    if not alert.message:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        alert.message = lines[0][:240] if lines else subject[:240]
    return alert
