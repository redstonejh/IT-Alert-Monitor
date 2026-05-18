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
    """Return the configured 0-100 base score from the ESET threat taxonomy."""
    cfg = _config(config)
    if not threat_name:
        return cfg.unknown_base_score

    slash_part = threat_name.split("/")[-1].lower()
    for keyword, score in _taxonomy(cfg):
        if re.search(r"\b" + re.escape(keyword) + r"\b", slash_part):
            return score

    return cfg.unknown_base_score


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

    with get_connection() as conn:
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

        distinct_days = conn.execute(
            "SELECT COUNT(DISTINCT substr(received_time, 1, 10)) AS c FROM alerts "
            "WHERE threat_name = ? AND hostname = ? AND received_time <= ?",
            (threat_name, hostname, now_iso),
        ).fetchone()["c"]
        if distinct_days >= 4:
            adjustment += cfg.persistence_4_day_adjustment
            reasons.append(f"persisting {distinct_days} days")
        elif distinct_days >= 2:
            adjustment += cfg.persistence_2_day_adjustment
            reasons.append(f"recurring across {distinct_days} days")

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

        host_alerts = conn.execute(
            "SELECT COUNT(*) AS c FROM alerts "
            "WHERE hostname = ? AND received_time >= ? AND received_time < ?",
            (hostname, host_window, now_iso),
        ).fetchone()["c"]
        if host_alerts >= cfg.host_alert_count_threshold:
            adjustment += cfg.host_alert_adjustment
            reasons.append(f"host has {host_alerts} alerts")

    failure_terms = ("failed", "failure", "unresolved", "not cleaned", "action required")
    success_terms = ("cleaned", "deleted", "resolved", "quarantined", "removed", "blocked", "terminated")
    status_blob = " ".join([action_taken, containment_status, resolved_status]).lower()
    if any(term in status_blob for term in failure_terms):
        adjustment += cfg.failure_adjustment
        reasons.append("action failed or threat unresolved")
    elif any(term in status_blob for term in success_terms):
        adjustment += cfg.success_adjustment
        reasons.append("contained by antivirus")

    return adjustment, reasons


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
    total = max(0, min(100, base + ctx))
    return total, severity_label(total, cfg), reasons
