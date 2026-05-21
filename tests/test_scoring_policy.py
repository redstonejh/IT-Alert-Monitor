from datetime import datetime, timezone

from app.database import init_db
from app.models import AppConfig, ParsedAlert
from app.rules import evaluate_alert, should_send_escalation
from app.scoring import base_score, score_alert
from app.storage import save_alert


def test_default_base_score_uses_reference_taxonomy(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATABASE_PATH", str(tmp_path / "alerts.db"))
    monkeypatch.setenv("APP_SECRET_KEY_PATH", str(tmp_path / "secret.key"))
    from app.config import get_app_settings

    get_app_settings.cache_clear()
    init_db()
    config = AppConfig(unknown_base_score=30)

    assert base_score("Win32/Ransomware.Sample", config) == 97
    assert base_score("Win32/Adware.Sample", config) == 15


def test_equal_base_mode_is_explicit_opt_out(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATABASE_PATH", str(tmp_path / "alerts.db"))
    monkeypatch.setenv("APP_SECRET_KEY_PATH", str(tmp_path / "secret.key"))
    from app.config import get_app_settings

    get_app_settings.cache_clear()
    init_db()
    config = AppConfig(unknown_base_score=30, use_taxonomy_weighting=False)

    assert base_score("Win32/Ransomware.Sample", config) == 30
    assert base_score("Win32/Adware.Sample", config) == 30


def test_unresolved_forces_critical_severity(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATABASE_PATH", str(tmp_path / "alerts.db"))
    monkeypatch.setenv("APP_SECRET_KEY_PATH", str(tmp_path / "secret.key"))
    from app.config import get_app_settings

    get_app_settings.cache_clear()
    init_db()
    config = AppConfig(
        unknown_base_score=10,
        severity_critical_threshold=95,
        use_taxonomy_weighting=False,
    )

    score, severity, reasons = score_alert(
        "Win32/LowSignal",
        "HOST-01",
        datetime.now(timezone.utc),
        action_taken="Remediation failed",
        containment_status="Failed",
        resolved_status="Unresolved",
        config=config,
    )

    assert score == 100
    assert severity == "Critical"
    assert "unresolved override forced Critical severity" in reasons


def test_unresolved_escalates_even_when_policy_score_would_be_low(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATABASE_PATH", str(tmp_path / "alerts.db"))
    monkeypatch.setenv("APP_SECRET_KEY_PATH", str(tmp_path / "secret.key"))
    from app.config import get_app_settings

    get_app_settings.cache_clear()
    init_db()
    config = AppConfig(escalation_cooldown_hours=24)
    alert = ParsedAlert(
        message_id="1",
        internet_message_id="<1@test>",
        received_time=datetime.now(timezone.utc),
        subject="ESET alert",
        sender="eset@example.test",
        client_name="Client",
        hostname="HOST-01",
        threat_name="Win32/LowSignal",
        severity="Medium",
        action_taken="No action performed",
        containment_status="Action required",
        resolved_status="Not resolved",
    )

    decision = evaluate_alert(alert, config)

    assert decision.should_alert is True
    assert decision.reason == "unresolved_override"
    assert should_send_escalation(decision, config) is True


def test_empty_identity_does_not_receive_history_adjustments(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATABASE_PATH", str(tmp_path / "alerts.db"))
    monkeypatch.setenv("APP_SECRET_KEY_PATH", str(tmp_path / "secret.key"))
    from app.config import get_app_settings

    get_app_settings.cache_clear()
    init_db()
    config = AppConfig(unknown_base_score=30, use_taxonomy_weighting=False)
    for index in range(4):
        save_alert(
            ParsedAlert(
                message_id=f"empty-{index}",
                internet_message_id=f"<empty-{index}@test>",
                received_time=datetime(2026, 1, index + 1, tzinfo=timezone.utc),
                subject="ESET alert",
                sender="eset@example.test",
                action_taken="Deleted",
            )
        )

    score, severity, reasons = score_alert(
        "",
        "",
        datetime(2026, 1, 5, tzinfo=timezone.utc),
        action_taken="Deleted",
        config=config,
    )

    assert score == 10
    assert severity == "Low"
    assert reasons == ["contained by antivirus"]


def test_persistent_repeat_same_host_forces_critical_even_when_terminated(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATABASE_PATH", str(tmp_path / "alerts.db"))
    monkeypatch.setenv("APP_SECRET_KEY_PATH", str(tmp_path / "secret.key"))
    from app.config import get_app_settings

    get_app_settings.cache_clear()
    init_db()
    config = AppConfig(
        repeat_threshold=3,
        use_taxonomy_weighting=True,
        severity_critical_threshold=95,
    )
    for index, received in enumerate(
        [
            datetime(2026, 5, 15, 16, 0, tzinfo=timezone.utc),
            datetime(2026, 5, 15, 16, 31, tzinfo=timezone.utc),
        ],
        start=1,
    ):
        save_alert(
            ParsedAlert(
                message_id=f"packed-{index}",
                internet_message_id=f"<packed-{index}@test>",
                received_time=received,
                subject="ESET alert",
                sender="eset@example.test",
                hostname="srm-fuelasst.srmdomain.local",
                threat_name="JS/Packed.Agent.W",
                action_taken="Connection terminated",
            )
        )

    score, severity, reasons = score_alert(
        "JS/Packed.Agent.W",
        "srm-fuelasst.srmdomain.local",
        datetime(2026, 5, 19, 20, 1, tzinfo=timezone.utc),
        action_taken="Connection terminated",
        config=config,
    )

    assert score == 100
    assert severity == "Critical"
    assert any("persistent repeat override" in reason for reason in reasons)
    assert "persistent repeat override forced Critical severity" in reasons


def test_old_spaced_repeat_does_not_force_critical(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATABASE_PATH", str(tmp_path / "alerts.db"))
    monkeypatch.setenv("APP_SECRET_KEY_PATH", str(tmp_path / "secret.key"))
    from app.config import get_app_settings

    get_app_settings.cache_clear()
    init_db()
    config = AppConfig(
        repeat_threshold=3,
        use_taxonomy_weighting=True,
        severity_critical_threshold=95,
    )
    for index, received in enumerate(
        [
            datetime(2026, 3, 26, 15, 17, tzinfo=timezone.utc),
            datetime(2026, 5, 7, 15, 17, tzinfo=timezone.utc),
            datetime(2026, 5, 7, 15, 47, tzinfo=timezone.utc),
        ],
        start=1,
    ):
        save_alert(
            ParsedAlert(
                message_id=f"phish-{index}",
                internet_message_id=f"<phish-{index}@test>",
                received_time=received,
                subject="ESET alert",
                sender="eset@example.test",
                hostname="maples-dan.maplesdomain.local",
                threat_name="QRCode/Phishing.A",
                action_taken="Contained infected files",
            )
        )

    score, severity, reasons = score_alert(
        "QRCode/Phishing.A",
        "maples-dan.maplesdomain.local",
        datetime(2026, 5, 15, 16, 42, tzinfo=timezone.utc),
        action_taken="Contained infected files",
        config=config,
    )

    assert score < 95
    assert severity != "Critical"
    assert not any("persistent repeat override" in reason for reason in reasons)
