import re
from datetime import datetime, timezone
from html import unescape

from app.models import ParsedAcronisAlert

FIELD_PATTERNS = {
    "severity": [
        r"Severity:\s*(.+)",
        r"Level:\s*(Critical|Error|Warning|Information)",
    ],
    "alert_type": [
        r"Alert(?:\s+type)?:\s*(.+)",
        r"Event(?:\s+type)?:\s*(.+)",
        r"Message(?:\s+type)?:\s*(.+)",
    ],
    "device": [
        r"Device(?:\s+name)?:\s*(.+)",
        r"Machine(?:\s+name)?:\s*(.+)",
        r"Computer(?:\s+name)?:\s*(.+)",
        r"Host(?:name)?:\s*(.+)",
    ],
    "plan_name": [
        r"Plan(?:\s+name)?:\s*(.+)",
        r"Backup plan:\s*(.+)",
        r"Protection plan:\s*(.+)",
    ],
    "alert_group": [
        r"Group:\s*(.+)",
        r"Org(?:anization)?(?:\s+unit)?:\s*(.+)",
    ],
    "account": [
        r"Account:\s*(.+)",
        r"Customer:\s*(.+)",
        r"Tenant:\s*(.+)",
        r"Client:\s*(.+)",
    ],
}

_SEVERITY_WORDS = ["critical", "error", "warning", "information"]


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


def _normalize_severity(raw: str, subject: str) -> str:
    combined = (raw + " " + subject).lower()
    for sev in _SEVERITY_WORDS:
        if sev in combined:
            return sev.capitalize()
    return raw.capitalize() if raw else ""


def parse_acronis_message(message: dict) -> ParsedAcronisAlert:
    body = message.get("body", {}).get("content", "") or ""
    text = _clean_body(body)
    subject = message.get("subject", "")
    sender = (
        message.get("from", {}).get("emailAddress", {}).get("address", "")
    )

    alert = ParsedAcronisAlert(
        message_id=message.get("id", ""),
        internet_message_id=message.get("internetMessageId", ""),
        received_time=_parse_time(message.get("receivedDateTime")),
        subject=subject,
        sender=sender,
        raw_email_body=text,
    )
    for field, patterns in FIELD_PATTERNS.items():
        setattr(alert, field, _extract(patterns, text))

    alert.severity = _normalize_severity(alert.severity, subject)
    return alert
