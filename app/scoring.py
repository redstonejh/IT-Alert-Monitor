"""
Threat severity scoring using ESET taxonomy plus local alert context.

The UI exposes these values on the Configure page. Scores stay on a 0-100 scale:
taxonomy score + context adjustments, clamped to 0..100, then bucketed into
Critical / High / Medium / Low by configured thresholds.
"""

import re
from datetime import datetime, timedelta, timezone

from app.database import get_connection
from app.models import AppConfig, DEFAULT_TAXONOMY_SCORES

PERSISTENT_REPEAT_OVERRIDE_PREFIX = "persistent repeat override"
PERSISTENT_REPEAT_OVERRIDE_WINDOW_DAYS = 7


def _config(config: AppConfig | None) -> AppConfig:
    if config is not None:
        return config
    from app.storage import get_config

    return get_config()


def _taxonomy(config: AppConfig) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    source = config.taxonomy_scores or DEFAULT_TAXONOMY_SCORES
    for line in source.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if "=" not in line:
            continue
        keyword, score_text = line.split("=", 1)
        keyword = keyword.strip().lower()
        try:
            score = int(score_text.strip())
        except ValueError:
            continue
        if keyword:
            rows.append((keyword, max(0, min(100, score))))
    # More specific compound terms should win before broad terms.
    return sorted(rows, key=lambda item: len(item[0]), reverse=True)


def base_score(threat_name: str, config: AppConfig | None = None) -> int:
    """Return the configured 0-100 starting score.

    The default model treats every threat name equally and lets containment,
    recurrence, persistence, spread, and velocity drive severity. Taxonomy
    weighting is preserved as an optional mode for teams that still want
    inherent threat-name risk to influence the starting score.
    """
    cfg = _config(config)
    if not cfg.use_taxonomy_weighting:
        return cfg.unknown_base_score
    if not threat_name:
        return cfg.unknown_base_score

    slash_part = threat_name.split("/")[-1].lower()
    for keyword, score in _taxonomy(cfg):
        if re.search(r"\b" + re.escape(keyword) + r"\b", slash_part):
            return score

    return cfg.unknown_base_score


def is_unresolved_or_failed(
    action_taken: str = "",
    containment_status: str = "",
    resolved_status: str = "",
) -> bool:
    """Return True when ESET says the issue still needs attention."""
    status_blob = " ".join([action_taken, containment_status, resolved_status]).lower()
    if not status_blob.strip():
        return False
    failure_patterns = (
        r"\bfailed\b",
        r"\bfailure\b",
        r"\bunresolved\b",
        r"\bnot\s+resolved\b",
        r"\bnot\s+cleaned\b",
        r"\bunable\s+to\s+(clean|remove|delete|quarantine|resolve)\b",
        r"\baction\s+required\b",
        r"\bremediation\s+(failed|required)\b",
    )
    return any(re.search(pattern, status_blob) for pattern in failure_patterns)


def is_successfully_contained(
    action_taken: str = "",
    containment_status: str = "",
    resolved_status: str = "",
) -> bool:
    """Return True only for clear positive containment language."""
    status_blob = " ".join([action_taken, containment_status, resolved_status]).lower()
    if is_unresolved_or_failed(action_taken, containment_status, resolved_status):
        return False
    success_patterns = (
        r"\bcleaned\b",
        r"\bdeleted\b",
        r"\bresolved\b",
        r"\bquarantined\b",
        r"\bremoved\b",
        r"\bblocked\b",
        r"\bterminated\b",
        r"\bcontained\b",
    )
    return any(re.search(pattern, status_blob) for pattern in success_patterns)


def severity_label(score: int, config: AppConfig | None = None) -> str:
    cfg = _config(config)
    if score >= cfg.severity_critical_threshold:
        return "Critical"
    if score >= cfg.severity_high_threshold:
        return "High"
    if score >= cfg.severity_medium_threshold:
        return "Medium"
    return "Low"


def contextual_adjustments(
    threat_name: str,
    hostname: str,
    received_time: datetime,
    action_taken: str,
    containment_status: str,
    resolved_status: str,
    config: AppConfig | None = None,
) -> tuple[int, list[str]]:
    """
    Query alert history and return (total_adjustment, reasons).
    All thresholds and points are configured from the UI.
    """
    cfg = _config(config)
    adjustment = 0
    reasons: list[str] = []
    now = received_time.astimezone(timezone.utc)
    now_iso = now.isoformat()
    repeat_window = (now - timedelta(hours=cfg.repeated_same_host_window_hours)).isoformat()
    campaign_window = (now - timedelta(hours=cfg.campaign_endpoint_window_hours)).isoformat()
    velocity_window = (now - timedelta(hours=cfg.velocity_window_hours)).isoformat()
    baseline_window = (now - timedelta(days=cfg.velocity_baseline_days)).isoformat()
    host_window = (now - timedelta(hours=cfg.host_alert_window_hours)).isoformat()
    history_window = (now - timedelta(days=max(1, cfg.lookback_days or 60))).isoformat()
    persistent_repeat_window = (
        now - timedelta(days=PERSISTENT_REPEAT_OVERRIDE_WINDOW_DAYS)
    ).isoformat()
    current_day = now.date().isoformat()

    with get_connection() as conn:
        same_recent = 0
        if threat_name and hostname:
            same_recent = conn.execute(
                "SELECT COUNT(*) AS c FROM alerts "
                "WHERE threat_name = ? AND hostname = ? AND received_time >= ? AND received_time < ?",
                (threat_name, hostname, repeat_window, now_iso),
            ).fetchone()["c"]
        if same_recent >= 3:
            adjustment += cfg.repeated_same_host_3_adjustment
            reasons.append(f"same threat hit this host {same_recent + 1} times")
        elif same_recent >= 2:
            adjustment += cfg.repeated_same_host_2_adjustment
            reasons.append(f"same threat hit this host {same_recent + 1} times")
        elif same_recent >= 1:
            adjustment += cfg.repeated_same_host_1_adjustment
            reasons.append(f"same threat hit this host {same_recent + 1} times")

        same_history_count = 0
        history_days: set[str] = set()
        persistent_repeat_count = 0
        persistent_repeat_days: set[str] = set()
        if threat_name and hostname:
            same_history = conn.execute(
                "SELECT substr(received_time, 1, 10) AS alert_day FROM alerts "
                "WHERE threat_name = ? AND hostname = ? AND received_time >= ? AND received_time < ?",
                (threat_name, hostname, history_window, now_iso),
            ).fetchall()
            same_history_count = len(same_history)
            history_days = {
                row["alert_day"]
                for row in same_history
                if row["alert_day"]
            }
            history_days.add(current_day)
            persistent_repeat_history = conn.execute(
                "SELECT substr(received_time, 1, 10) AS alert_day FROM alerts "
                "WHERE threat_name = ? AND hostname = ? AND received_time >= ? AND received_time < ?",
                (threat_name, hostname, persistent_repeat_window, now_iso),
            ).fetchall()
            persistent_repeat_count = len(persistent_repeat_history)
            persistent_repeat_days = {
                row["alert_day"]
                for row in persistent_repeat_history
                if row["alert_day"]
            }
            persistent_repeat_days.add(current_day)

        total_persistent_repeat = persistent_repeat_count + 1 if threat_name and hostname else 0
        distinct_days = len(history_days)
        distinct_persistent_repeat_days = len(persistent_repeat_days)
        persistent_repeat_threshold = max(3, cfg.repeat_threshold or 3)
        if total_persistent_repeat >= persistent_repeat_threshold and distinct_persistent_repeat_days >= 2:
            reasons.append(
                f"{PERSISTENT_REPEAT_OVERRIDE_PREFIX}: same threat hit this host "
                f"{total_persistent_repeat} times across {distinct_persistent_repeat_days} days "
                f"within {PERSISTENT_REPEAT_OVERRIDE_WINDOW_DAYS} days"
            )

        hosts_in_window = 0
        if threat_name:
            hosts_in_window = conn.execute(
                "SELECT COUNT(DISTINCT hostname) AS c FROM alerts "
                "WHERE threat_name = ? AND received_time >= ? AND received_time <= ? AND hostname != ''",
                (threat_name, campaign_window, now_iso),
            ).fetchone()["c"]
        if hosts_in_window >= 5:
            adjustment += cfg.campaign_endpoint_5_adjustment
            reasons.append(f"spreading to {hosts_in_window} endpoints")
        elif hosts_in_window >= 3:
            adjustment += cfg.campaign_endpoint_3_adjustment
            reasons.append(f"spreading to {hosts_in_window} endpoints")
        elif hosts_in_window >= 2:
            adjustment += cfg.campaign_endpoint_2_adjustment

        if distinct_days >= 4:
            adjustment += cfg.persistence_4_day_adjustment
            reasons.append(f"persisting {distinct_days} days")
        elif distinct_days >= 2:
            adjustment += cfg.persistence_2_day_adjustment
            reasons.append(f"recurring across {distinct_days} days")

        count_velocity = 0
        count_baseline = 0
        if threat_name:
            count_velocity = conn.execute(
                "SELECT COUNT(*) AS c FROM alerts "
                "WHERE threat_name = ? AND received_time >= ? AND received_time <= ?",
                (threat_name, velocity_window, now_iso),
            ).fetchone()["c"]
            count_baseline = conn.execute(
                "SELECT COUNT(*) AS c FROM alerts "
                "WHERE threat_name = ? AND received_time >= ? AND received_time < ?",
                (threat_name, baseline_window, campaign_window),
            ).fetchone()["c"]
        recent_rate = count_velocity / max(1, cfg.velocity_window_hours)
        baseline_hours = max(1, (cfg.velocity_baseline_days * 24) - cfg.campaign_endpoint_window_hours)
        baseline_rate = count_baseline / baseline_hours if count_baseline else 0
        if (
            recent_rate > baseline_rate * cfg.velocity_multiplier
            and count_velocity >= cfg.velocity_min_count
        ):
            adjustment += cfg.velocity_adjustment
            reasons.append("alert frequency accelerating")

        host_alerts = 0
        if hostname:
            host_alerts = conn.execute(
                "SELECT COUNT(*) AS c FROM alerts "
                "WHERE hostname = ? AND received_time >= ? AND received_time < ?",
                (hostname, host_window, now_iso),
            ).fetchone()["c"]
        if host_alerts >= cfg.host_alert_count_threshold:
            adjustment += cfg.host_alert_adjustment
            reasons.append(f"host has {host_alerts} alerts")

    if is_unresolved_or_failed(action_taken, containment_status, resolved_status):
        adjustment += cfg.failure_adjustment
        reasons.append("action failed or threat unresolved")
    elif is_successfully_contained(action_taken, containment_status, resolved_status):
        adjustment += cfg.success_adjustment
        reasons.append("contained by antivirus")

    return adjustment, reasons


def has_persistent_repeat_override(reasons: list[str]) -> bool:
    return any(reason.startswith(PERSISTENT_REPEAT_OVERRIDE_PREFIX) for reason in reasons)


def score_alert(
    threat_name: str,
    hostname: str,
    received_time: datetime,
    action_taken: str = "",
    containment_status: str = "",
    resolved_status: str = "",
    config: AppConfig | None = None,
) -> tuple[int, str, list[str]]:
    """Compute score, severity label, and context reasons from current config."""
    cfg = _config(config)
    base = base_score(threat_name, cfg)
    ctx, reasons = contextual_adjustments(
        threat_name,
        hostname,
        received_time,
        action_taken,
        containment_status,
        resolved_status,
        cfg,
    )
    if is_unresolved_or_failed(action_taken, containment_status, resolved_status):
        total = 100
        if "unresolved override forced Critical severity" not in reasons:
            reasons.append("unresolved override forced Critical severity")
    elif has_persistent_repeat_override(reasons):
        total = 100
        if "persistent repeat override forced Critical severity" not in reasons:
            reasons.append("persistent repeat override forced Critical severity")
    else:
        total = max(0, min(100, base + ctx))
    return total, severity_label(total, cfg), reasons


def scoring_breakdown(
    threat_name: str,
    hostname: str,
    received_time: datetime,
    action_taken: str = "",
    containment_status: str = "",
    resolved_status: str = "",
    config: AppConfig | None = None,
) -> dict[str, object]:
    cfg = _config(config)
    base = base_score(threat_name, cfg)
    ctx, reasons = contextual_adjustments(
        threat_name,
        hostname,
        received_time,
        action_taken,
        containment_status,
        resolved_status,
        cfg,
    )
    unresolved_override = is_unresolved_or_failed(action_taken, containment_status, resolved_status)
    persistent_repeat_override = has_persistent_repeat_override(reasons)
    override = unresolved_override or persistent_repeat_override
    score = 100 if override else max(0, min(100, base + ctx))
    label = severity_label(score, cfg)
    if unresolved_override and "unresolved override forced Critical severity" not in reasons:
        reasons.append("unresolved override forced Critical severity")
    if persistent_repeat_override and "persistent repeat override forced Critical severity" not in reasons:
        reasons.append("persistent repeat override forced Critical severity")
    return {
        "base_score": base,
        "context_adjustment": ctx,
        "score": score,
        "severity": label,
        "reasons": reasons,
        "unresolved_override": unresolved_override,
        "persistent_repeat_override": persistent_repeat_override,
        "taxonomy_weighting": cfg.use_taxonomy_weighting,
    }
