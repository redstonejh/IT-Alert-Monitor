import re
from datetime import datetime, timezone
from html import unescape

from app.models import ParsedAlert

FIELD_PATTERNS = {
    "client_name": [r"Client(?: name)?:\s*(.+)", r"Customer:\s*(.+)"],
    "hostname": [r"Host(?:name)?:\s*(.+)", r"Computer:\s*(.+)", r"Device:\s*(.+)"],
    "computer_name": [r"Computer name:\s*(.+)", r"Computer:\s*(.+)"],
    "username": [r"User(?:name)?:\s*(.+)", r"Logged user:\s*(.+)"],
    "threat_name": [r"Threat(?: name)?:\s*(.+)", r"Malware:\s*(.+)"],
    "detection_name": [r"Detection(?: name)?:\s*(.+)", r"Detection:\s*(.+)"],
    "severity": [r"Severity:\s*(.+)", r"Threat level:\s*(.+)"],
    "action_taken": [r"Action performed:\s*(.+)", r"Action(?: taken)?:\s*(.+)", r"Action:\s*(.+)"],
    "containment_status": [r"Containment(?: status)?:\s*(.+)", r"Status:\s*(.+)"],
    "resolved_status": [r"Resolved(?: status)?:\s*(.+)", r"Resolution:\s*(.+)", r"Result:\s*(.+)"],
    "scan_type": [r"Scan(?: type)?:\s*(.+)"],
    "ip_address": [r"IP(?: address)?:\s*([0-9a-fA-F:.]+)"],
    "operating_system": [r"Operating system:\s*(.+)", r"OS:\s*(.+)"],
}


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


def parse_graph_message(message: dict) -> ParsedAlert:
    body = message.get("body", {}).get("content", "") or ""
    text = _clean_body(body)
    sender = (
        message.get("from", {})
        .get("emailAddress", {})
        .get("address", "")
    )
    alert = ParsedAlert(
        message_id=message.get("id", ""),
        internet_message_id=message.get("internetMessageId", ""),
        received_time=_parse_time(message.get("receivedDateTime")),
        subject=message.get("subject", ""),
        sender=sender,
        raw_email_body=text,
    )
    for field, patterns in FIELD_PATTERNS.items():
        setattr(alert, field, _extract(patterns, text))
    if not alert.threat_name:
        alert.threat_name = alert.detection_name
    if not alert.hostname:
        alert.hostname = alert.computer_name
    # Infer action_taken from subject when email body has no action field
    if not alert.action_taken:
        subject_lower = alert.subject.lower()
        if any(w in subject_lower for w in ("was blocked", "was cleaned", "was deleted", "was removed", "was quarantined")):
            alert.action_taken = "Cleaned"
        elif any(w in subject_lower for w in ("failed", "unresolved", "not cleaned")):
            alert.action_taken = "Remediation failed"
    return alert
