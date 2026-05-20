from dataclasses import dataclass

import requests

from app.company_abbreviations import abbreviate_company
from app.models import ParsedAlert
from app.rules import reason_label


@dataclass(frozen=True)
class TeamsSendResult:
    status_code: int
    response_text: str


class TeamsNotifier:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def test(self) -> bool:
        self.send_text("ESET alert parser test notification.")
        return True

    def format_alert(self, alert: ParsedAlert, reason: str, count: int) -> str:
        title = f"ESET escalation: {alert.severity or 'Unknown'} - {alert.threat_name or 'Unknown threat'}"
        lines = [
            f"**{title}**",
            f"Reason: {reason_label(reason)}",
            f"Client: {abbreviate_company(alert.client_name) or 'Unknown'}",
            f"Hostname: {alert.hostname or 'Unknown'}",
            f"User: {alert.username or 'Unknown'}",
            f"Action: {alert.action_taken or 'Unknown'}",
            f"Status: {alert.containment_status or alert.resolved_status or 'Unknown'}",
            f"Matching count: {count}",
            f"Received: {alert.received_time.isoformat()}",
        ]
        return "\n\n".join(lines)

    def send_alert(self, alert: ParsedAlert, reason: str, count: int) -> str:
        text = self.format_alert(alert, reason, count)
        self.send_text(text)
        return text

    @staticmethod
    def _adaptive_card_payload(text: str) -> dict:
        title = "ESET Alert Monitor"
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines and lines[0].startswith("**") and lines[0].endswith("**"):
            title = lines.pop(0).strip("*")
        body: list[dict] = [
            {
                "type": "TextBlock",
                "text": title,
                "weight": "Bolder",
                "size": "Large",
                "color": "Attention",
                "wrap": True,
            }
        ]
        for line in lines:
            body.append({"type": "TextBlock", "text": line, "wrap": True, "spacing": "Small"})
        return {
            "type": "message",
            # New Teams Workflow webhook templates commonly map this field directly
            # into a "post message" action. Legacy Incoming Webhook ignores it and
            # renders the Adaptive Card attachment below.
            "text": text,
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.2",
                        "body": body,
                    },
                }
            ],
        }

    def send_text(self, text: str) -> TeamsSendResult:
        if not self.webhook_url:
            raise ValueError("Teams webhook URL is required.")
        response = requests.post(self.webhook_url, json=self._adaptive_card_payload(text), timeout=20)
        if response.status_code >= 400:
            detail = response.text[:300] if response.text else ""
            raise RuntimeError(f"Teams webhook request failed with status {response.status_code}. {detail}")
        return TeamsSendResult(response.status_code, response.text[:300] if response.text else "")
