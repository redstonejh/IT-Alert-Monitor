from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates

from app.acronis_scanner import DEFAULT_LOOKBACK_DAYS, run_acronis_scan, run_acronis_scan_range
from app.company_abbreviations import abbreviate_company, company_full_name
from app.storage import (
    get_acronis_alert,
    get_acronis_config,
    get_setting,
    get_state,
    list_acronis_alerts,
    list_current_acronis_escalation_cases,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
RANGE_PRESETS = [
    {"days": 1, "label": "Today", "short": "Today"},
    {"days": 7, "label": "Last 7 days", "short": "7d"},
    {"days": 30, "label": "Last 30 days", "short": "30d"},
    {"days": 60, "label": "Last 60 days", "short": "60d"},
    {"days": 90, "label": "Last 90 days", "short": "90d"},
    {"days": 180, "label": "Last 6 months", "short": "6mo"},
    {"days": 365, "label": "Last year", "short": "1yr"},
]
METRIC_LABELS = {
    "": "Alerts",
    "critical": "Critical alerts",
    "error": "Error alerts",
    "warning": "Warning alerts",
    "information": "Information alerts",
}
_ACRONIS_DATE_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},\s+\d{4},\s+\d{1,2}:\d{2}:\d{2}\s+[AP]M\b",
    flags=re.IGNORECASE,
)
_SERVER_HINT_RE = re.compile(
    r"\b(server|srv|dc|ad|domain|sql|exchange|exch|fs|file|nas|backup|bdr|rds|rdp|"
    r"vmhost|hyper|esxi|host|terminal|trinity)\b",
    flags=re.IGNORECASE,
)
_WORKSTATION_HINT_RE = re.compile(
    r"\b(desktop|laptop|notebook|workstation|office|mgr|pc)\b",
    flags=re.IGNORECASE,
)
_CATEGORY_PATTERNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "storage_failure",
        "Storage failure",
        (
            r"\bsmart\b",
            r"\bbad sectors?\b",
            r"\bdisk (?:failure|failed|error|health)\b",
            r"\bdrive (?:failure|failed|error|health)\b",
            r"\bhard disk\b",
            r"\bio error\b|\bi/o error\b",
            r"\bvolume .*(?:failed|error|unavailable)\b",
        ),
    ),
    (
        "repository_failure",
        "Repository issue",
        (
            r"\brepository\b.*\b(?:failed|unavailable|not available|cannot|error|corrupt)",
            r"\bbackup (?:storage|location|destination)\b.*\b(?:failed|unavailable|not available|cannot|error)",
            r"\barchive\b.*\b(?:corrupt|damaged|failed|unavailable)",
            r"\bbackup chain\b.*\b(?:corrupt|damaged|failed)",
        ),
    ),
    (
        "capacity_full",
        "Capacity full",
        (
            r"\bnot enough (?:free )?space\b",
            r"\bout of space\b",
            r"\bquota\b.*\b(?:exceeded|full|limit)",
            r"\b(?:storage|disk|repository|destination)\b.*\bfull\b",
        ),
    ),
    (
        "auth_or_license",
        "Auth/license issue",
        (
            r"\bcredential",
            r"\bauthentication\b|\bauthorization\b|\bunauthorized\b",
            r"\baccess denied\b",
            r"\bpassword\b.*\b(?:expired|invalid|failed)",
            r"\blicen[sc]e\b.*\b(?:expired|invalid|missing|exceeded)",
        ),
    ),
    (
        "agent_or_service_down",
        "Agent/service down",
        (
            r"\bagent\b.*\b(?:stopped|offline|not running|unavailable|failed)",
            r"\bservice\b.*\b(?:stopped|not running|failed|unavailable)",
        ),
    ),
    (
        "transient_maintenance",
        "Transient/maintenance",
        (
            r"\brestart of the operating system\b",
            r"\boperating system (?:restart|reboot|shutdown)\b",
            r"\b(?:system|machine|computer|server|host) (?:was )?(?:restarted|rebooted|shut down|shutdown)\b",
            r"\b(?:restart|reboot|shutdown)\b.*\b(?:operating system|machine|computer|server|host)\b",
            r"\bclosed backup window\b",
            r"\bbackup window (?:closed|expired|ended)\b",
            r"\boperation was canceled\b",
            r"\bbackup was canceled\b",
            r"\buser canceled\b",
            r"\bcancelled by user\b",
        ),
    ),
    (
        "connectivity",
        "Connectivity",
        (
            r"\bno connection\b",
            r"\boffline\b",
            r"\bcannot connect\b|\bcan't connect\b",
            r"\bunreachable\b",
            r"\bnetwork\b.*\b(?:error|unavailable|timeout|failed)",
            r"\btimeout\b",
        ),
    ),
    (
        "backup_failed_generic",
        "Generic backup failure",
        (
            r"\bbackup failed\b",
            r"\bactivity has failed\b",
            r"\bfailed due to\b",
            r"\bbackup was canceled\b",
        ),
    ),
)
ACRONIS_TRIAGE_DEFAULTS: dict[str, int] = {
    "acronis_triage_critical_threshold": 90,
    "acronis_triage_high_threshold": 60,
    "acronis_triage_medium_threshold": 25,
    "acronis_triage_status_critical": 20,
    "acronis_triage_status_error": 15,
    "acronis_triage_status_warning": 5,
    "acronis_triage_status_information": -80,
    "acronis_triage_storage_failure": 60,
    "acronis_triage_repository_failure": 55,
    "acronis_triage_capacity_full": 50,
    "acronis_triage_auth_or_license": 42,
    "acronis_triage_agent_or_service_down": 35,
    "acronis_triage_transient_maintenance": -45,
    "acronis_triage_backup_failed_generic": 18,
    "acronis_triage_connectivity": 8,
    "acronis_triage_stale_offline": -15,
    "acronis_triage_success_or_info": -90,
    "acronis_triage_unknown": -20,
    "acronis_triage_backup_failed_adjustment": 20,
    "acronis_triage_backup_not_failed_adjustment": -45,
    "acronis_triage_server_adjustment": 25,
    "acronis_triage_endpoint_connectivity_adjustment": -15,
    "acronis_triage_maintenance_adjustment": -20,
    "acronis_triage_new_pattern_adjustment": 25,
    "acronis_triage_repeat_pattern_adjustment": -30,
    "acronis_triage_spread_adjustment": 25,
    "acronis_triage_offline_7_day_adjustment": -18,
    "acronis_triage_offline_14_day_adjustment": -35,
    "acronis_triage_offline_30_day_adjustment": -45,
}


def _pacific_fallback(utc: datetime) -> datetime:
    year = utc.year

    def nth_sunday(y: int, month: int, n: int) -> datetime:
        first = datetime(y, month, 1, tzinfo=timezone.utc)
        days_to_sunday = (6 - first.weekday()) % 7
        return first + timedelta(days=days_to_sunday + 7 * (n - 1))

    dst_start = nth_sunday(year, 3, 2) + timedelta(hours=10)
    dst_end = nth_sunday(year, 11, 1) + timedelta(hours=9)
    offset = timedelta(hours=-7 if dst_start <= utc < dst_end else -8)
    return utc + offset


def _format_datetime(value: object) -> str:
    if not value:
        return ""
    text = str(value)
    try:
        utc = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return text
    try:
        local = utc.astimezone(ZoneInfo("America/Los_Angeles"))
    except ZoneInfoNotFoundError:
        local = _pacific_fallback(utc)
    hour = local.hour % 12 or 12
    return f"{local:%m/%d/%y} {hour}:{local:%M %p}"


def _format_date_compact(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%m/%d/%y")
    except (ValueError, TypeError):
        return value or ""


def _range_display(start: str, end: str) -> str:
    return f"{_format_date_compact(start)} - {_format_date_compact(end)}"


def _severity_class(severity: object) -> str:
    normalized = str(severity or "unknown").strip().lower()
    return {
        "critical": "critical",
        "error": "high",
        "warning": "medium",
        "information": "low",
        "info": "low",
    }.get(normalized, "unknown")


def _severity_display(severity: object) -> str:
    normalized = str(severity or "").strip().lower()
    return {
        "critical": "Critical",
        "error": "Error",
        "warning": "Warning",
        "information": "Information",
        "info": "Information",
    }.get(normalized, str(severity or "Unknown").strip().title() or "Unknown")


def _acronis_triage_config() -> dict[str, int]:
    config: dict[str, int] = {}
    for key, default in ACRONIS_TRIAGE_DEFAULTS.items():
        raw = get_setting(key, decrypt=False)
        try:
            config[key] = int(raw) if str(raw).strip() else default
        except ValueError:
            config[key] = default
    return config


def _backup_failed_display(value: object) -> str:
    if isinstance(value, str):
        return "Fail" if value.strip().lower() in {"1", "true", "yes", "y"} else "Pass"
    return "Fail" if value else "Pass"


def _search_matches(query: str, values: list[object]) -> bool:
    terms = [term for term in re.split(r"\s+", query.strip().lower()) if term]
    if not terms:
        return True
    haystack = " ".join(str(value or "") for value in values).lower()
    return all(term in haystack for term in terms)


def _raw_text(row: dict) -> str:
    return re.sub(r"\s+", " ", str(row.get("raw_email_body") or "").replace("\xa0", " ")).strip()


def _label_value(label: str, text: str) -> str:
    stop_labels = (
        "Plan name",
        "Where to back up",
        "Group",
        "Account",
        "View in web console",
        "If you have",
        "Subject",
        "From",
        "To",
        "Sent",
    )
    stop = "|".join(re.escape(item) for item in stop_labels if item.lower() != label.lower())
    match = re.search(
        rf"\b{re.escape(label)}\b\s+(.+?)(?=\s+(?:{stop})\b|$)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().strip(".,;")
    return ""


def _company_display(row: dict) -> str:
    text = _raw_text(row)
    company = str(
        row.get("alert_group")
        or row.get("account")
        or _label_value("Group", text)
        or _label_value("Account", text)
        or "Unknown"
    ).strip()
    return abbreviate_company(company)


def _company_full_display(row: dict) -> str:
    text = _raw_text(row)
    company = str(
        row.get("alert_group")
        or row.get("account")
        or _label_value("Group", text)
        or _label_value("Account", text)
        or row.get("company_display")
        or "Unknown"
    ).strip()
    return company_full_name(company)


def _alert_date_display(row: dict) -> str:
    parsed = _alert_event_datetime(row)
    if parsed:
        hour = parsed.hour % 12 or 12
        return f"{parsed:%m/%d/%y} {hour}:{parsed:%M %p}"
    return str(row.get("received_display") or row.get("received_time") or "").strip()


def _alert_event_datetime(row: dict) -> datetime | None:
    text = _raw_text(row)
    body_dates = [
        match.group(0) for match in _ACRONIS_DATE_RE.finditer(text)
    ]
    alert_date = body_dates[-1] if body_dates else ""
    display = str(row.get("alert_date") or alert_date or "").strip()
    if display:
        try:
            return datetime.strptime(display, "%B %d, %Y, %I:%M:%S %p")
        except ValueError:
            return None
    return None


def _row_in_event_range(row: dict, start: str, end: str) -> bool:
    event_dt = _alert_event_datetime(row)
    if not event_dt:
        return True
    event_date = event_dt.date().isoformat()
    return (not start or event_date >= start) and (not end or event_date <= end)


def _acronis_stats_from_rows(rows: list[dict]) -> dict[str, int]:
    stats = {"critical": 0, "error": 0, "warning": 0, "information": 0}
    for row in rows:
        severity = _status_display(row).strip().lower()
        if severity in stats:
            stats[severity] += 1
    return stats


def _machine_display(row: dict) -> str:
    text = _raw_text(row)
    quoted = re.search(r"machine\s+'([^']+)'", text, flags=re.IGNORECASE)
    return str(
        row.get("device")
        or _label_value("Device", text)
        or (quoted.group(1).strip() if quoted else "")
        or "Unknown"
    ).strip()


def _backup_failed_value(row: dict) -> bool:
    value = row.get("backup_failed")
    if isinstance(value, str) and value.strip():
        return value.strip().lower() in {"1", "true", "yes", "y"}
    if value:
        return True
    text = "\n".join(str(row.get(field) or "") for field in ("alert_type", "reason", "raw_email_body")).lower()
    return any(
        marker in text
        for marker in (
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
    )


def _offline_days(row: dict) -> int:
    text = " ".join(str(row.get(field) or "") for field in ("reason_display", "reason", "alert_type", "raw_email_body"))
    match = re.search(
        r"(?:no connection|offline)(?: with machine '[^']+')? for (?:more than )?(\d+) days",
        text,
        flags=re.IGNORECASE,
    )
    return int(match.group(1)) if match else 0


def _machine_is_server_like(machine: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", machine.lower())
    if not normalized.strip():
        return False
    if _SERVER_HINT_RE.search(normalized):
        return True
    if _WORKSTATION_HINT_RE.search(normalized):
        return False
    return False


def _acronis_category(row: dict) -> tuple[str, str]:
    text = " ".join(
        str(row.get(field) or "")
        for field in (
            "reason_display",
            "reason",
            "alert_type",
            "subject",
            "raw_email_body",
        )
    ).lower()
    if not _backup_failed_value(row) and row.get("severity_display", "").lower() in {"information", "info"}:
        return "success_or_info", "Informational"
    for category, label, patterns in _CATEGORY_PATTERNS:
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            if category == "connectivity" and _offline_days(row) >= 14:
                return "stale_offline", "Stale offline"
            return category, label
    if _backup_failed_value(row):
        return "backup_failed_generic", "Generic backup failure"
    return "unknown", "Unknown"


def _triage_fingerprint(row: dict) -> tuple[str, str, str, str]:
    reason = re.sub(r"\b\d+\b", "#", str(row.get("reason_display") or row.get("reason") or "").lower())
    return (
        str(row.get("company_display") or "").strip().lower(),
        str(row.get("machine_display") or "").strip().lower(),
        str(row.get("triage_category") or "").strip().lower(),
        reason,
    )


def _triage_context(rows: list[dict]) -> dict[str, object]:
    fingerprints: Counter = Counter()
    company_category_machines: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        category, label = _acronis_category(row)
        row["triage_category"] = category
        row["triage_category_label"] = label
        fingerprints[_triage_fingerprint(row)] += 1
        company_category_machines[
            (str(row.get("company_display") or "").lower(), category)
        ].add(str(row.get("machine_display") or "").lower())
    return {
        "fingerprints": fingerprints,
        "company_category_machines": company_category_machines,
    }


def _triage_decision(
    row: dict,
    context: dict[str, object] | None = None,
    config: dict[str, int] | None = None,
) -> dict[str, object]:
    context = context or {}
    config = config or ACRONIS_TRIAGE_DEFAULTS
    severity = str(row.get("severity_display") or row.get("severity") or "").strip().lower()
    category = str(row.get("triage_category") or _acronis_category(row)[0])
    category_label = str(row.get("triage_category_label") or _acronis_category(row)[1])
    backup_failed = _backup_failed_value(row)
    machine = str(row.get("machine_display") or row.get("device") or "")
    server_like = _machine_is_server_like(machine)
    offline_days = _offline_days(row)
    fingerprint_count = int((context.get("fingerprints") or {}).get(_triage_fingerprint(row), 1))
    company_category_machines = context.get("company_category_machines") or {}
    spread_count = len(company_category_machines.get((str(row.get("company_display") or "").lower(), category), set()))
    score = {
        "critical": config["acronis_triage_status_critical"],
        "error": config["acronis_triage_status_error"],
        "warning": config["acronis_triage_status_warning"],
        "information": config["acronis_triage_status_information"],
        "info": config["acronis_triage_status_information"],
    }.get(severity, 0)
    reasons: list[str] = []
    score_reasons: list[str] = []
    category_weights = {
        "storage_failure": config["acronis_triage_storage_failure"],
        "repository_failure": config["acronis_triage_repository_failure"],
        "capacity_full": config["acronis_triage_capacity_full"],
        "auth_or_license": config["acronis_triage_auth_or_license"],
        "agent_or_service_down": config["acronis_triage_agent_or_service_down"],
        "transient_maintenance": config["acronis_triage_transient_maintenance"],
        "backup_failed_generic": config["acronis_triage_backup_failed_generic"],
        "connectivity": config["acronis_triage_connectivity"],
        "stale_offline": config["acronis_triage_stale_offline"],
        "success_or_info": config["acronis_triage_success_or_info"],
        "unknown": config["acronis_triage_unknown"],
    }
    category_score = category_weights.get(category, 0)
    score += category_score
    reasons.append(category_label)
    score_reasons.append(f"Acronis status {severity or 'unknown'} contributed {score - category_score}.")
    score_reasons.append(f"{category_label} category contributed {category_score}.")
    if backup_failed:
        score += config["acronis_triage_backup_failed_adjustment"]
        reasons.append("backup failed")
        score_reasons.append(f"Backup failed added {config['acronis_triage_backup_failed_adjustment']}.")
    else:
        score += config["acronis_triage_backup_not_failed_adjustment"]
        reasons.append("backup not failed")
        score_reasons.append(f"Backup not failed added {config['acronis_triage_backup_not_failed_adjustment']}.")
    if server_like:
        score += config["acronis_triage_server_adjustment"]
        reasons.append("server-like machine")
        score_reasons.append(f"Server-like machine added {config['acronis_triage_server_adjustment']}.")
    elif category in {"connectivity", "stale_offline"}:
        score += config["acronis_triage_endpoint_connectivity_adjustment"]
        reasons.append("endpoint-like connectivity noise")
        score_reasons.append(f"Endpoint-like connectivity pattern added {config['acronis_triage_endpoint_connectivity_adjustment']}.")
    elif category == "transient_maintenance":
        score += config["acronis_triage_maintenance_adjustment"]
        reasons.append("maintenance-like interruption")
        score_reasons.append(f"Maintenance-like interruption added {config['acronis_triage_maintenance_adjustment']}.")
    if fingerprint_count <= 1:
        score += config["acronis_triage_new_pattern_adjustment"]
        reasons.append("new pattern")
        score_reasons.append(f"New company/machine/reason pattern added {config['acronis_triage_new_pattern_adjustment']}.")
    else:
        score += config["acronis_triage_repeat_pattern_adjustment"]
        reasons.append("repeat pattern")
        score_reasons.append(f"Repeated same pattern added {config['acronis_triage_repeat_pattern_adjustment']}.")
    if spread_count >= 2:
        spread_adjustment = config["acronis_triage_spread_adjustment"]
        score += spread_adjustment
        reasons.append(f"{spread_count} machines affected")
        score_reasons.append(f"{spread_count} machines affected added {spread_adjustment}.")
    if offline_days:
        if offline_days >= 30:
            score += config["acronis_triage_offline_30_day_adjustment"]
            reasons.append(f"stale {offline_days}d offline")
            score_reasons.append(f"Offline for {offline_days} days added {config['acronis_triage_offline_30_day_adjustment']}.")
        elif offline_days >= 14:
            score += config["acronis_triage_offline_14_day_adjustment"]
            reasons.append(f"stale {offline_days}d offline")
            score_reasons.append(f"Offline for {offline_days} days added {config['acronis_triage_offline_14_day_adjustment']}.")
        elif offline_days >= 7:
            score += config["acronis_triage_offline_7_day_adjustment"]
            reasons.append(f"{offline_days}d offline")
            score_reasons.append(f"Offline for {offline_days} days added {config['acronis_triage_offline_7_day_adjustment']}.")
    high_confidence = category in {
        "storage_failure",
        "repository_failure",
        "capacity_full",
        "auth_or_license",
        "agent_or_service_down",
    }
    stale_noise = category == "stale_offline" and not server_like
    non_actionable = category in {"success_or_info", "unknown", "transient_maintenance"} or stale_noise
    actionable = backup_failed and not non_actionable
    would_push = score >= config["acronis_triage_critical_threshold"] and actionable and (high_confidence or spread_count >= 2)
    if would_push:
        label = "Escalate"
        css_class = "critical"
        score_reasons.append("Push gate passed; eligible for Teams escalation with one message per company/machine per 24 hours.")
    elif score >= config["acronis_triage_high_threshold"] and actionable:
        label = "Review"
        css_class = "high"
        score_reasons.append("High/review threshold met, but push gate did not pass.")
    elif score >= config["acronis_triage_medium_threshold"]:
        label = "Dashboard only"
        css_class = "medium"
        score_reasons.append("Medium threshold met; kept on dashboard.")
    else:
        label = "Suppress noise"
        css_class = "low"
        score_reasons.append("Below medium threshold or non-actionable; treated as noise.")
    summary = ", ".join(reasons[:4])
    return {
        "score": max(-100, min(140, score)),
        "label": label,
        "class": css_class,
        "category": category,
        "category_label": category_label,
        "summary": summary,
        "score_reasons": score_reasons,
        "would_push": would_push,
        "teams_paused": False,
    }


def _derived_severity_from_triage(
    triage: dict[str, object],
    config: dict[str, int] | None = None,
) -> tuple[str, str]:
    config = config or ACRONIS_TRIAGE_DEFAULTS
    try:
        score = int(triage.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    if score >= config["acronis_triage_critical_threshold"] and triage.get("would_push"):
        return "Critical", "critical"
    if score >= config["acronis_triage_high_threshold"] and str(triage.get("label")) == "Review":
        return "High", "high"
    if score >= config["acronis_triage_medium_threshold"]:
        return "Medium", "medium"
    return "Low", "low"


def _reason_display(row: dict) -> str:
    if row.get("reason"):
        return str(row["reason"]).strip()
    text = _raw_text(row)
    no_connection = re.search(r"no connection(?: with machine '[^']+')? for (\d+) days", text, flags=re.IGNORECASE)
    if no_connection:
        return f"No connection for {no_connection.group(1)} days"
    offline = re.search(r"offline for (?:more than )?(\d+) days", text, flags=re.IGNORECASE)
    if offline:
        return f"No connection for {offline.group(1)} days"
    canceled = re.search(r"backup was canceled due to (.+?)(?:\.|$)", text, flags=re.IGNORECASE)
    if canceled:
        return f"Backup canceled due to {canceled.group(1).strip()}"
    backup_failed = re.search(
        r"Backup failed\s+" + _ACRONIS_DATE_RE.pattern + r"\s+(.+?)(?=\s+Device\b|\s+Plan name\b|\s+Group\b|$)",
        text,
        flags=re.IGNORECASE,
    )
    if backup_failed:
        return backup_failed.group(1).strip().strip(".")
    return str(row.get("alert_type") or "").strip()


def _status_display(row: dict) -> str:
    text = _raw_text(row)
    match = re.search(
        r"\b(Critical|Error|Warning|Information)\b\s+(?:Backup failed|Machine is offline|The backup)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).capitalize()
    return _severity_display(row.get("severity"))


def _today_utc() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _range_start(days: int) -> str:
    today = _today_utc()
    if days <= 1:
        return today.date().isoformat()
    return (today - timedelta(days=days - 1)).date().isoformat()


def _safe_range_days(value: str) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LOOKBACK_DAYS
    allowed = {preset["days"] for preset in RANGE_PRESETS}
    return days if days in allowed else DEFAULT_LOOKBACK_DAYS


def _custom_range(start_value: str, end_value: str) -> tuple[str, str] | None:
    if not start_value or not end_value:
        return None
    try:
        start = datetime.strptime(start_value, "%Y-%m-%d").date()
        end = datetime.strptime(end_value, "%Y-%m-%d").date()
    except ValueError:
        return None
    if start > end:
        start, end = end, start
    return start.isoformat(), end.isoformat()


def _safe_metric(value: str) -> str:
    return value if value in METRIC_LABELS else ""


def _ensure_acronis_scan_coverage(days: int) -> tuple[bool, int]:
    desired_start = _range_start(days)
    today = _today_utc().date().isoformat()
    coverage_start = get_state("acronis_scan_coverage_start")
    coverage_end = get_state("acronis_scan_coverage_end")
    processed = 0
    scanned = False

    if not coverage_start:
        result = run_acronis_scan_range(desired_start, today)
        return bool(result.get("scan_attempted")), result.get("processed", 0)

    if desired_start < coverage_start:
        previous_day = (
            datetime.strptime(coverage_start, "%Y-%m-%d") - timedelta(days=1)
        ).date().isoformat()
        result = run_acronis_scan_range(desired_start, previous_day)
        processed += result.get("processed", 0)
        scanned = scanned or bool(result.get("scan_attempted"))

    if not coverage_end or coverage_end < today:
        result = run_acronis_scan()
        processed += result.get("processed", 0)
        scanned = scanned or bool(result.get("scan_attempted"))

    return scanned, processed


@router.get("/acronis")
def acronis_dashboard(request: Request):
    acronis_config = get_acronis_config()
    active_days = _safe_range_days(request.query_params.get("range", str(DEFAULT_LOOKBACK_DAYS)))
    active_metric = _safe_metric(request.query_params.get("metric", ""))
    search_query = request.query_params.get("q", "").strip()
    custom_range = _custom_range(request.query_params.get("start", ""), request.query_params.get("end", ""))
    if custom_range:
        view_start, view_end = custom_range
        range_query = f"start={view_start}&end={view_end}"
        coverage_days = max(1, (_today_utc().date() - datetime.strptime(view_start, "%Y-%m-%d").date()).days + 1)
    else:
        view_start = _range_start(active_days)
        view_end = _today_utc().date().isoformat()
        range_query = f"range={active_days}"
        coverage_days = active_days
    auto_scanned = False
    auto_processed = 0
    auto_scan_failed = False
    if acronis_config.mailbox_address:
        try:
            auto_scanned, auto_processed = _ensure_acronis_scan_coverage(coverage_days)
        except Exception:
            auto_scan_failed = True
    last_scan_display = _format_datetime(get_state("acronis_last_scan_time"))
    last_scan_error = get_state("acronis_last_scan_error")
    triage_config = _acronis_triage_config()
    raw_alerts = [
        row for row in list_acronis_alerts(limit=500, start=view_start, end=view_end)
        if _row_in_event_range(row, view_start, view_end)
    ]
    for row in raw_alerts:
        row["received_display"] = _format_datetime(row.get("received_time"))
        row["date_display"] = _alert_date_display(row)
        row["company_display"] = _company_display(row)
        row["company_full_display"] = _company_full_display(row)
        row["machine_display"] = _machine_display(row)
        row["backup_failed_display"] = _backup_failed_display(_backup_failed_value(row))
        row["reason_display"] = _reason_display(row)
        row["acronis_status_display"] = _status_display(row)
        row["acronis_status_class"] = _severity_class(row["acronis_status_display"])
        row["severity_display"] = row["acronis_status_display"]
        row["severity_class"] = row["acronis_status_class"]
    triage_context = _triage_context(raw_alerts)
    for row in raw_alerts:
        triage = _triage_decision(row, triage_context, triage_config)
        row["triage_score"] = triage["score"]
        row["triage_label"] = triage["label"]
        row["triage_class"] = triage["class"]
        row["triage_category"] = triage["category"]
        row["triage_category_label"] = triage["category_label"]
        row["triage_summary"] = triage["summary"]
        row["triage_score_reasons"] = triage["score_reasons"]
        row["triage_would_push"] = triage["would_push"]
        derived_display, derived_class = _derived_severity_from_triage(triage, triage_config)
        row["derived_severity_display"] = derived_display
        row["derived_severity_class"] = derived_class
    stats = _acronis_stats_from_rows(raw_alerts)
    alerts = []
    for row in raw_alerts:
        row_status = _status_display(row)
        if active_metric and row_status.lower() != active_metric:
            continue
        if search_query and not _search_matches(
            search_query,
            [
                row.get("received_display"),
                row.get("date_display"),
                row.get("company_display"),
                row.get("company_full_display"),
                row.get("machine_display"),
                row.get("backup_failed_display"),
                row.get("reason_display"),
                row.get("derived_severity_display"),
                row.get("severity_display"),
                row.get("acronis_status_display"),
                row.get("triage_label"),
                row.get("triage_category_label"),
                row.get("alert_group"),
                row.get("account"),
                row.get("device"),
                row.get("plan_name"),
                row.get("alert_date"),
                row.get("subject"),
                row.get("sender"),
                row.get("raw_email_body"),
            ],
        ):
            continue
        alerts.append(row)
    triage_alerts = [
        row for row in alerts
        if row.get("triage_would_push") or row.get("triage_label") == "Review"
    ][:8]
    acronis_escalations = list_current_acronis_escalation_cases(50, start=view_start, end=view_end)
    for item in acronis_escalations:
        item["created_display"] = _format_datetime(item.get("last_alerted_at") or item.get("created_at"))
        item["company_display"] = _company_display(item)
        item["company_full_display"] = _company_full_display(item)
        item["machine_display"] = _machine_display(item)
        item["backup_failed_display"] = _backup_failed_display(_backup_failed_value(item))
        item["reason_display"] = _reason_display(item)
        item["reason_label"] = "Critical severity"
    return templates.TemplateResponse(
        "acronis_dashboard.html",
        {
            "request": request,
            "acronis_config": acronis_config,
            "last_scan_display": last_scan_display,
            "last_scan_error": last_scan_error,
            "acronis_stats": stats,
            "acronis_alerts": alerts,
            "acronis_triage_alerts": triage_alerts,
            "acronis_escalations": acronis_escalations,
            "triage_config": triage_config,
            "active_days": active_days,
            "active_metric": active_metric,
            "search_query": search_query,
            "custom_range": bool(custom_range),
            "range_query": range_query,
            "range_display": _range_display(view_start, view_end),
            "metric_label": METRIC_LABELS[active_metric],
            "range_presets": RANGE_PRESETS,
            "view_start": view_start,
            "view_end": view_end,
            "auto_scanned": auto_scanned,
            "auto_processed": auto_processed,
            "auto_scan_failed": auto_scan_failed,
        },
    )


@router.get("/acronis/alerts/{alert_id}")
def acronis_alert_detail(request: Request, alert_id: int):
    alert = get_acronis_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Acronis alert not found")
    alert["received_display"] = _format_datetime(alert.get("received_time"))
    alert["date_display"] = _alert_date_display(alert)
    alert["company_display"] = _company_display(alert)
    alert["company_full_display"] = _company_full_display(alert)
    alert["machine_display"] = _machine_display(alert)
    alert["backup_failed_display"] = _backup_failed_display(_backup_failed_value(alert))
    alert["reason_display"] = _reason_display(alert)
    alert["acronis_status_display"] = _status_display(alert)
    alert["acronis_status_class"] = _severity_class(alert["acronis_status_display"])
    alert["severity_display"] = alert["acronis_status_display"]
    alert["severity_class"] = alert["acronis_status_class"]
    alert["triage_category"], alert["triage_category_label"] = _acronis_category(alert)
    triage_config = _acronis_triage_config()
    triage = _triage_decision(alert, config=triage_config)
    alert["triage_score"] = triage["score"]
    alert["triage_label"] = triage["label"]
    alert["triage_class"] = triage["class"]
    alert["triage_summary"] = triage["summary"]
    alert["triage_score_reasons"] = triage["score_reasons"]
    alert["triage_would_push"] = triage["would_push"]
    derived_display, derived_class = _derived_severity_from_triage(triage, triage_config)
    alert["derived_severity_display"] = derived_display
    alert["derived_severity_class"] = derived_class
    return templates.TemplateResponse(
        "acronis_alert_detail.html",
        {
            "request": request,
            "alert": alert,
        },
    )
