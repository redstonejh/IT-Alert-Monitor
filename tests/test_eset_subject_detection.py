from app.graph_client import GraphClient
from app.models import AppConfig
from app.parser import parse_graph_message


def _message(subject: str) -> dict:
    return {
        "id": "eset-subject-1",
        "internetMessageId": "<eset-subject-1@test>",
        "receivedDateTime": "2026-05-20T16:00:00Z",
        "subject": subject,
        "from": {"emailAddress": {"address": "report@protect.eset.com"}},
        "body": {"content": ""},
    }


def test_eset_detection_subject_passes_saved_eset_subject_filter():
    config = AppConfig(
        eset_sender_filter="report@protect.eset.com",
        eset_subject_filter="ESET",
    )
    message = _message("Malicious file JS/Redirector.TFE was detected on computer TRL-WS01")

    assert GraphClient(config)._local_filter([message]) == [message]


def test_eset_detection_subject_parses_threat_and_host():
    alert = parse_graph_message(
        _message("Malicious file JS/Redirector.TFE was detected on computer TRL-WS01")
    )

    assert alert.threat_name == "JS/Redirector.TFE"
    assert alert.detection_name == "JS/Redirector.TFE"
    assert alert.hostname == "TRL-WS01"
    assert alert.computer_name == "TRL-WS01"
