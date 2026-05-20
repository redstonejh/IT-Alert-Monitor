import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

import msal
import requests

from app.storage import get_setting, save_setting

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
DELEGATED_SCOPES = ["User.Read", "Mail.Read"]
logger = logging.getLogger(__name__)


class GraphClient:
    def __init__(self, config) -> None:
        self.config = config

    def _authority(self) -> str:
        if not self.config.tenant_id:
            return "https://login.microsoftonline.com/common"
        return f"https://login.microsoftonline.com/{self.config.tenant_id}"

    def _confidential_app(self, token_cache: msal.SerializableTokenCache | None = None) -> msal.ConfidentialClientApplication:
        if not (self.config.client_id and self.config.client_secret):
            raise ValueError("Graph client ID and client secret are required.")
        app = msal.ConfidentialClientApplication(
            self.config.client_id,
            authority=self._authority(),
            client_credential=self.config.client_secret,
            token_cache=token_cache,
        )
        return app

    def _app_token(self) -> str:
        if not self.config.tenant_id:
            raise ValueError("Tenant ID is required for app credential mode.")
        app = self._confidential_app()
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in result:
            raise RuntimeError(result.get("error_description", "Could not acquire Graph token."))
        return str(result["access_token"])

    def _delegated_token(self) -> str:
        if not self.config.client_id:
            raise ValueError("Client ID is required for Microsoft sign-in.")
        cache = msal.SerializableTokenCache()
        serialized = get_setting("oauth_token_cache")
        if serialized:
            cache.deserialize(serialized)
        if self.config.client_secret:
            app = self._confidential_app(cache)
        else:
            app = msal.PublicClientApplication(self.config.client_id, authority=self._authority(), token_cache=cache)
        accounts = app.get_accounts()
        if not accounts:
            raise ValueError("No Microsoft account is signed in. Use Settings > Sign in with Microsoft.")
        result = app.acquire_token_silent(DELEGATED_SCOPES, account=accounts[0])
        if cache.has_state_changed:
            save_setting("oauth_token_cache", cache.serialize(), sensitive=True)
        if not result or "access_token" not in result:
            raise RuntimeError("Could not refresh Microsoft sign-in. Sign in again from Settings.")
        return str(result["access_token"])

    def _token(self) -> str:
        if self.config.auth_mode == "delegated":
            return self._delegated_token()
        return self._app_token()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}", "Accept": "application/json"}

    def test_connection(self) -> bool:
        url = f"{GRAPH_ROOT}/me?$select=id,userPrincipalName" if self.config.auth_mode == "delegated" else f"{GRAPH_ROOT}/organization?$select=id"
        response = requests.get(url, headers=self._headers(), timeout=20)
        response.raise_for_status()
        return True

    def test_mailbox(self) -> bool:
        mailbox_root = self._mailbox_root()
        folder = self.config.mail_folder.strip()
        url = (
            f"{mailbox_root}/mailFolders/{quote(folder)}"
            if folder
            else f"{mailbox_root}/mailFolders?{urlencode({'includeHiddenFolders': 'true', '$top': '1'})}"
        )
        response = requests.get(url, headers=self._headers(), timeout=20)
        response.raise_for_status()
        return True

    def _mailbox_root(self) -> str:
        if self.config.auth_mode == "delegated" and not self.config.mailbox_address:
            return f"{GRAPH_ROOT}/me"
        if not self.config.mailbox_address:
            raise ValueError("Mailbox address is required for app credential mailbox access.")
        return f"{GRAPH_ROOT}/users/{quote(self.config.mailbox_address)}"

    @staticmethod
    def _graph_datetime(value: str) -> str:
        if not value:
            return value
        if value.endswith("Z") or "+" in value:
            return value
        return f"{value}:00Z" if len(value) == 16 else f"{value}Z"

    def iter_matching_messages(self) -> list[dict]:
        start = self.config.start_date
        if not start:
            start_dt = datetime.now(timezone.utc) - timedelta(days=self.config.lookback_days)
            start = start_dt.isoformat().replace("+00:00", "Z")
        logger.info("Graph scan: mailbox=%s auth=%s lookback_start=%s",
                    getattr(self.config, "mailbox_address", "?"),
                    getattr(self.config, "auth_mode", "?"),
                    start[:19])
        filters = [f"receivedDateTime ge {self._graph_datetime(start)}"]
        select = "id,internetMessageId,receivedDateTime,subject,from,body"
        folder = self.config.mail_folder.strip()
        if folder:
            urls = [self._messages_url(folder, select, filters)]
            logger.info("Graph scan: targeting single folder=%s", folder)
        else:
            folder_ids = self._list_mail_folder_ids()
            urls = [self._messages_url(fid, select, filters) for fid in folder_ids]
            logger.info("Graph scan: scanning %d folders (all)", len(folder_ids))
        messages: list[dict] = []
        headers = self._headers()
        seen_message_ids: set[str] = set()
        raw_total = 0
        for url in urls:
            while url:
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                payload = response.json()
                page = payload.get("value", [])
                raw_total += len(page)
                for message in self._local_filter(page):
                    message_id = message.get("id", "")
                    if message_id and message_id in seen_message_ids:
                        continue
                    seen_message_ids.add(message_id)
                    messages.append(message)
                url = payload.get("@odata.nextLink")
        logger.info("Graph scan: fetched %d raw messages, %d passed local filter", raw_total, len(messages))
        return messages

    def _messages_url(self, folder_id_or_name: str, select: str, filters: list[str]) -> str:
        query = urlencode(
            {
                "$select": select,
                "$top": "50",
                "$orderby": "receivedDateTime asc",
                "$filter": " and ".join(filters),
            }
        )
        return f"{self._mailbox_root()}/mailFolders/{quote(folder_id_or_name, safe='')}/messages?{query}"

    def _list_mail_folder_ids(self) -> list[str]:
        mailbox_root = self._mailbox_root()
        headers = self._headers()
        folder_ids: list[str] = []
        seen: set[str] = set()

        def collect(url: str) -> None:
            while url:
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                payload = response.json()
                for folder in payload.get("value", []):
                    folder_id = folder.get("id", "")
                    if not folder_id or folder_id in seen:
                        continue
                    seen.add(folder_id)
                    folder_ids.append(folder_id)
                    child_url = (
                        f"{mailbox_root}/mailFolders/{quote(folder_id, safe='')}/childFolders?"
                        f"{urlencode({'includeHiddenFolders': 'true', '$top': '100'})}"
                    )
                    collect(child_url)
                url = payload.get("@odata.nextLink")

        collect(f"{mailbox_root}/mailFolders?{urlencode({'includeHiddenFolders': 'true', '$top': '100'})}")
        return folder_ids

    def _local_filter(self, messages: list[dict]) -> list[dict]:
        import re
        sender_filter = (getattr(self.config, "sender_filter", None) or
                         getattr(self.config, "eset_sender_filter", "")).lower().strip()
        subject_filter = (getattr(self.config, "subject_filter", None) or
                          getattr(self.config, "eset_subject_filter", "")).lower().strip()
        subject_pattern = re.compile(r'\b' + re.escape(subject_filter) + r'\b') if subject_filter else None

        def is_eset_detection_subject(sender: str, subject: str) -> bool:
            return (
                "report@protect.eset.com" in sender
                and " was detected on computer " in subject
                and any(kind in subject for kind in ("malicious file", "suspicious application", "potentially unwanted"))
            )

        matched: list[dict] = []
        for message in messages:
            sender = (
                message.get("from", {})
                .get("emailAddress", {})
                .get("address", "")
                .lower()
            )
            subject = (message.get("subject", "") or "").lower()
            if sender_filter and sender_filter not in sender:
                logger.info("Local filter DROP sender_mismatch: sender=%s subject=%.60s", sender, subject)
                continue
            if subject_pattern and not subject_pattern.search(subject) and not is_eset_detection_subject(sender, subject):
                logger.info("Local filter DROP subject_mismatch: sender=%s subject=%.60s", sender, subject)
                continue
            matched.append(message)
        return matched
