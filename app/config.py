from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    database_path: str = Field("./data/eset_alerts.db", validation_alias="APP_DATABASE_PATH")
    secret_key_path: str = Field("./data/secret.key", validation_alias="APP_SECRET_KEY_PATH")
    log_path: str = Field("./logs/app.log", validation_alias="APP_LOG_PATH")
    poll_interval_seconds: int = Field(60, validation_alias="APP_POLL_INTERVAL_SECONDS")

    graph_tenant_id: str | None = Field(None, validation_alias="GRAPH_TENANT_ID")
    graph_client_id: str | None = Field(None, validation_alias="GRAPH_CLIENT_ID")
    graph_client_secret: str | None = Field(None, validation_alias="GRAPH_CLIENT_SECRET")
    graph_mailbox_address: str | None = Field(None, validation_alias="GRAPH_MAILBOX_ADDRESS")
    graph_mail_folder: str = Field("", validation_alias="GRAPH_MAIL_FOLDER")
    teams_webhook_url: str | None = Field(None, validation_alias="TEAMS_WEBHOOK_URL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def ensure_dirs(self) -> None:
        for file_path in (self.database_path, self.secret_key_path, self.log_path):
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_app_settings() -> AppSettings:
    settings = AppSettings()
    settings.ensure_dirs()
    return settings
