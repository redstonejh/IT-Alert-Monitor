import re
from dataclasses import replace
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
_ACRONIS_BODY_MARKERS = (
    "cloud.acronis.com",
    "acronis.com/support",
    "manage data protection",
)
_ACRONIS_STATUS_REPORT_RE = re.compile(
    r"\bDAILY STATUS REPORT\b.*\(\s*Critical:\s*\d+,\s*Error:\s*\d+,\s*Warning:\s*\d+,\s*Information:\s*\d+\s*\)",
    flags=re.IGNORECASE,
)
_ACRONIS_DATE_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},\s+\d{4},\s+\d{1,2}:\d{2}:\d{2}\s+[AP]M\b",
    flags=re.IGNORECASE,
)


def _clean_body(body: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", body, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = text.replace("\xa0", "\n")
    text = re.sub(r"(?<=\s)[?•](?=\s)", "\n", text)
    lines = []
    for line in text.splitlines():
        if re.match(r"\s*(?:from|sent|to|subject):", line, flags=re.IGNORECASE):
            lines.append(line)
            continue
        lines.append(
            re.sub(
                r"\s+(Device|Plan name|Where to back up|Group|Account|View in web console)\b",
                r"\n\1",
                line,
                flags=re.IGNORECASE,
            )
        )
    text = "\n".join(lines)
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


def _message_text_parts(message: dict) -> tuple[str, str, str]:
    body = message.get("body", {}).get("content", "") or ""
    text = _clean_body(body)
    graph_subject = message.get("subject", "") or ""
    forwarded_subject = _extract_forwarded_header("Subject", text)
    graph_sender = message.get("from", {}).get("emailAddress", {}).get("address", "") or ""
    forwarded_sender = _extract_forwarded_header("From", text)
    return text, "\n".join([graph_subject, forwarded_subject]), "\n".join([graph_sender, forwarded_sender])


def is_acronis_message(message: dict) -> bool:
    """Return True only for Acronis notifications, including forwarded copies."""
    text, subject_text, sender_text = _message_text_parts(message)
    combined = "\n".join([subject_text, sender_text, text]).lower()
    subject_lower = subject_text.lower()
    sender_lower = sender_text.lower()

    if "acronis" in sender_lower or any(marker in combined for marker in _ACRONIS_BODY_MARKERS):
        return True
    if _ACRONIS_STATUS_REPORT_RE.search(subject_text):
        return True
    if (
        ("backup failed" in subject_lower or "backup succeeded with warnings" in subject_lower)
        and "(group:" in subject_lower
        and ("(machine:" in subject_lower or "(plan:" in subject_lower)
    ):
        return True
    return False


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


def _is_daily_item_start(line: str) -> bool:
    normalized = line.strip().lower()
    return (
        normalized == "backup failed"
        or normalized.startswith("backup failed ")
        or normalized == "backup succeeded with warnings"
        or normalized.startswith("backup succeeded with warnings ")
        or normalized.startswith("machine is offline")
        or normalized.startswith("the backup was canceled")
    )


def _daily_item_segments(lines: list[str]) -> list[tuple[str, list[str]]]:
    starts: list[tuple[int, str]] = []
    current_severity = ""
    for index, line in enumerate(lines):
        normalized = line.strip().lower()
        if normalized in _SEVERITY_WORDS:
            current_severity = normalized.capitalize()
            continue
        if _is_daily_item_start(line):
            starts.append((index, current_severity))

    segments: list[tuple[str, list[str]]] = []
    for position, (start, severity) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        segment: list[str] = []
        for line in lines[start:end]:
            if line.lower().startswith("if you have any questions"):
                break
            segment.append(line)
        if segment:
            segments.append((severity, segment))
    return segments


def _extract_alert_date(lines: list[str]) -> str:
    for line in lines:
        if line.lower().startswith(("subject:", "from:", "to:", "sent:")):
            continue
        match = _ACRONIS_DATE_RE.search(line)
        if match:
            return match.group(0)
    return ""


def _extract_severity_line(lines: list[str]) -> str:
    for line in lines:
        normalized = line.strip().lower()
        if normalized in _SEVERITY_WORDS:
            return normalized.capitalize()
    return ""


def _extract_machine(text: str, lines: list[str], subject: str, device: str) -> str:
    machine = _extract_subject_field("device", subject) or device or _extract_label_value("Device", lines)
    if machine:
        return machine
    match = re.search(r"machine\s+'([^']+)'", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _derive_backup_failed(text: str, alert_type: str, severity: str) -> bool:
    combined = f"{alert_type}\n{severity}\n{text}".lower()
    failure_markers = (
        "backup failed",
        "backups of this machine are stopped",
        "backups are stopped",
        "backup is stopped",
        "failed",
        "missed",
        "unsuccessful",
        "unavailable",
        "blocked",
    )
    return any(marker in combined for marker in failure_markers)


def _derive_reason(text: str, lines: list[str], alert_type: str) -> str:
    no_connection = re.search(r"no connection(?: with machine '[^']+')? for (\d+) days", text, flags=re.IGNORECASE)
    if no_connection:
        return f"No connection for {no_connection.group(1)} days"
    offline = re.search(r"offline for (?:more than )?(\d+) days", text, flags=re.IGNORECASE)
    if offline:
        return f"No connection for {offline.group(1)} days"
    canceled = re.search(r"backup was canceled due to (.+?)(?:\.|$)", text, flags=re.IGNORECASE)
    if canceled:
        return f"Backup canceled due to {canceled.group(1).strip()}"
    failed = re.search(r"backup failed(?: because| due to)?[:\s-]*(.+?)(?:\.|$)", text, flags=re.IGNORECASE)
    if failed and failed.group(1).strip():
        return failed.group(1).strip().capitalize()

    skip_values = {
        "critical",
        "error",
        "warning",
        "information",
        "show details",
        "manage data protection",
        alert_type.lower(),
    }
    for line in lines:
        lower = line.lower()
        if lower in skip_values:
            continue
        if _ACRONIS_DATE_RE.search(line):
            continue
        if lower.startswith(("from:", "subject:", "device ", "group ", "account ", "plan name")):
            continue
        return line[:160]
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
    if raw.strip().lower() in _SEVERITY_WORDS:
        return raw.strip().capitalize()
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
    alerts = parse_acronis_messages(message)
    return alerts[0]


def parse_acronis_messages(message: dict) -> list[ParsedAcronisAlert]:
    body = message.get("body", {}).get("content", "") or ""
    text = _clean_body(body)
    graph_subject = message.get("subject", "")
    forwarded_subject = _extract_forwarded_header("Subject", text)
    subject = forwarded_subject or graph_subject
    forwarded_sender = _extract_forwarded_header("From", text)
    sender = (
        message.get("from", {}).get("emailAddress", {}).get("address", "")
    )

    base_alert = ParsedAcronisAlert(
        message_id=message.get("id", ""),
        internet_message_id=message.get("internetMessageId", ""),
        received_time=_parse_time(message.get("receivedDateTime")),
        subject=subject,
        sender=forwarded_sender or sender,
        raw_email_body=text,
    )
    for field, patterns in FIELD_PATTERNS.items():
        setattr(base_alert, field, _extract(patterns, text))

    lines = _clean_lines(text)
    base_alert.alert_type = base_alert.alert_type or _subject_alert_type(subject)
    base_alert.alert_group = (
        _extract_subject_field("alert_group", subject)
        or base_alert.alert_group
        or _extract_label_value("Group", lines)
    )
    base_alert.account = (
        _extract_subject_field("account", subject)
        or base_alert.account
        or _extract_label_value("Account", lines)
    )

    daily_segments = _daily_item_segments(lines) if base_alert.alert_type == "Daily status report" else []
    if not daily_segments:
        base_alert.alert_date = _extract_alert_date(lines)
        base_alert.device = _extract_machine(text, lines, subject, base_alert.device)
        base_alert.plan_name = (
            _extract_subject_field("plan_name", subject)
            or base_alert.plan_name
            or _extract_label_value("Plan name", lines)
        )
        base_alert.severity = _normalize_severity(base_alert.severity or _extract_severity_line(lines), subject, text)
        base_alert.backup_failed = _derive_backup_failed(text, base_alert.alert_type, base_alert.severity)
        base_alert.reason = _derive_reason(text, lines, base_alert.alert_type)
        return [base_alert]

    alerts: list[ParsedAcronisAlert] = []
    inherited_severity = ""
    for index, (segment_severity, segment_lines) in enumerate(daily_segments, start=1):
        if segment_severity:
            inherited_severity = segment_severity
        segment_text = "\n".join(segment_lines)
        alert = replace(base_alert)
        if index > 1:
            alert.message_id = f"{base_alert.message_id}#{index}"
        alert.raw_email_body = "\n".join(
            [line for line in lines if line.lower().startswith(("from:", "sent:", "to:", "subject:"))]
            + segment_lines
        )
        alert.alert_date = _extract_alert_date(segment_lines) or _extract_alert_date(lines)
        alert.device = _extract_machine(segment_text, segment_lines, subject, "")
        alert.plan_name = _extract_subject_field("plan_name", subject) or _extract_label_value("Plan name", segment_lines)
        alert.alert_group = base_alert.alert_group or _extract_label_value("Group", segment_lines)
        alert.account = base_alert.account or _extract_label_value("Account", segment_lines)
        alert.severity = _normalize_severity(segment_severity or inherited_severity, subject, segment_text)
        alert.backup_failed = _derive_backup_failed(segment_text, alert.alert_type, alert.severity)
        alert.reason = _derive_reason(segment_text, segment_lines, alert.alert_type)
        alerts.append(alert)
    return alerts
