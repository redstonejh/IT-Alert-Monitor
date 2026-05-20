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
_SUBJECT_FIELD_PATTERNS = {
    "alert_group": r"\(group:\s*([^)]+)\)",
    "account": r"\(backup account:\s*([^)]+)\)",
    "device": r"\(machine:\s*([^)]+)\)",
    "plan_name": r"\(plan:\s*([^)]+)\)",
}


def _clean_body(body: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", body, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _extract(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip().strip(".,;")
    return ""


def _extract_forwarded_header(name: str, text: str) -> str:
    match = re.search(rf"^\s*{re.escape(name)}:\s*(.+)$", text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_subject_field(field: str, subject: str) -> str:
    pattern = _SUBJECT_FIELD_PATTERNS.get(field)
    if not pattern:
        return ""
    match = re.search(pattern, subject, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _extract_label_value(label: str, lines: list[str]) -> str:
    label_lower = label.lower()
    for index, line in enumerate(lines):
        clean = line.strip().strip(":")
        if clean.lower() == label_lower:
            for candidate in lines[index + 1:index + 4]:
                if candidate.strip():
                    return candidate.strip().strip(".,;")
        if clean.lower().startswith(label_lower + " "):
            value = clean[len(label):].strip(" :")
            if value:
                return value.strip().strip(".,;")
    return ""


def _subject_alert_type(subject: str) -> str:
    upper = subject.upper()
    if "DAILY STATUS REPORT" in upper:
        return "Daily status report"
    if "BACKUP SUCCEEDED WITH WARNINGS" in upper:
        return "Backup succeeded with warnings"
    if "BACKUP FAILED" in upper:
        return "Backup failed"
    return ""


def _extract_message(lines: list[str], alert_type: str, device: str) -> str:
    lowered_type = alert_type.lower()
    for index, line in enumerate(lines):
        if lowered_type and line.lower() == lowered_type:
            start = index + 1
            if device and start < len(lines) and lines[start].lower() == device.lower():
                start += 1
            for candidate in lines[start:start + 5]:
                if candidate and candidate.lower() not in {"show details", "manage data protection"}:
                    return candidate[:300]
        if line.lower() in {"warning", "error", "critical", "information"}:
            for candidate in lines[index + 1:index + 4]:
                if candidate and not re.match(r"^[A-Z][a-z]+ \d{1,2}, \d{4},", candidate):
                    return candidate[:300]
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


def _normalize_severity(raw: str, subject: str, text: str = "") -> str:
    combined = (raw + " " + subject + " " + text[:500]).lower()
    if "backup failed" in combined:
        return "Error"
    if "succeeded with warnings" in combined or re.search(r"\bwarning\b", combined):
        return "Warning"
    for sev in _SEVERITY_WORDS:
        if sev in combined:
            return sev.capitalize()
    return raw.capitalize() if raw else ""


def parse_acronis_message(message: dict) -> ParsedAcronisAlert:
    body = message.get("body", {}).get("content", "") or ""
    text = _clean_body(body)
    graph_subject = message.get("subject", "")
    forwarded_subject = _extract_forwarded_header("Subject", text)
    subject = forwarded_subject or graph_subject
    forwarded_sender = _extract_forwarded_header("From", text)
    sender = (
        message.get("from", {}).get("emailAddress", {}).get("address", "")
    )

    alert = ParsedAcronisAlert(
        message_id=message.get("id", ""),
        internet_message_id=message.get("internetMessageId", ""),
        received_time=_parse_time(message.get("receivedDateTime")),
        subject=subject,
        sender=forwarded_sender or sender,
        raw_email_body=text,
    )
    for field, patterns in FIELD_PATTERNS.items():
        setattr(alert, field, _extract(patterns, text))

    lines = _clean_lines(text)
    alert.alert_type = alert.alert_type or _subject_alert_type(subject)
    alert.device = _extract_subject_field("device", subject) or alert.device or _extract_label_value("Device", lines)
    alert.plan_name = _extract_subject_field("plan_name", subject) or alert.plan_name or _extract_label_value("Plan name", lines)
    alert.alert_group = _extract_subject_field("alert_group", subject) or alert.alert_group or _extract_label_value("Group", lines)
    alert.account = _extract_subject_field("account", subject) or alert.account or _extract_label_value("Account", lines)
    alert.severity = _normalize_severity(alert.severity, subject, text)
    return alert
