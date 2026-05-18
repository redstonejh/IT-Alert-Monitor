from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any


DEFAULT_TAXONOMY_SCORES = """ransomware=97
rootkit=95
backdoor=90
rat=90
keylogger=85
psw=82
spy=80
stealer=80
infostealer=80
exploit=78
worm=76
trojan=74
phishing=72
dropper=70
cryptominer=60
downloader=55
injector=52
obfuscated=45
packed=40
redirector=38
riskware=25
pua=18
adware=15
cookie=8"""


@dataclass(slots=True)
class AppConfig:
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    mailbox_address: str = ""
    mail_folder: str = ""
    auth_mode: str = "app"
    oauth_account: str = ""
    teams_webhook_url: str = ""
    teams_dry_run: bool = True
    eset_sender_filter: str = ""
    eset_subject_filter: str = "ESET"
    repeat_threshold: int = 3
    repeat_window_hours: int = 24
    escalation_cooldown_hours: int = 24
    lookback_days: int = 60
    start_date: str = ""
    poll_interval_seconds: int = 60
    taxonomy_scores: str = DEFAULT_TAXONOMY_SCORES
    unknown_base_score: int = 30
    severity_critical_threshold: int = 95
    severity_high_threshold: int = 70
    severity_medium_threshold: int = 45
    repeated_same_host_window_hours: int = 24
    repeated_same_host_1_adjustment: int = 20
    repeated_same_host_2_adjustment: int = 40
    repeated_same_host_3_adjustment: int = 60
    campaign_endpoint_window_hours: int = 24
    campaign_endpoint_2_adjustment: int = 8
    campaign_endpoint_3_adjustment: int = 18
    campaign_endpoint_5_adjustment: int = 30
    persistence_2_day_adjustment: int = 10
    persistence_4_day_adjustment: int = 20
    velocity_window_hours: int = 6
    velocity_baseline_days: int = 7
    velocity_multiplier: int = 5
    velocity_min_count: int = 3
    velocity_adjustment: int = 10
    host_alert_window_hours: int = 24
    host_alert_count_threshold: int = 10
    host_alert_adjustment: int = 10
    failure_adjustment: int = 20
    success_adjustment: int = -20


@dataclass(slots=True)
class ParsedAlert:
    message_id: str
    internet_message_id: str
    received_time: datetime
    subject: str
    sender: str
    client_name: str = ""
    hostname: str = ""
    computer_name: str = ""
    username: str = ""
    threat_name: str = ""
    detection_name: str = ""
    severity: str = ""
    action_taken: str = ""
    containment_status: str = ""
    resolved_status: str = ""
    scan_type: str = ""
    ip_address: str = ""
    operating_system: str = ""
    raw_email_body: str = ""
    score: int = 0

    def as_dict(self) -> dict[str, Any]:
        data = {field.name: getattr(self, field.name) for field in fields(self)}
        data["received_time"] = self.received_time.isoformat()
        return data


@dataclass(slots=True)
class EscalationDecision:
    should_alert: bool
    reason: str
    fingerprint: str
    severity_rank: int
    count: int
