from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / "config" / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = ""
    payment_mode: str = "manual"  # manual | auto
    database_url: str = "sqlite+aiosqlite:///data/marketsignal.db"

    # Ссылка на оплату (ЮMoney/крипта) — показывается при выборе тарифа
    payment_link: str = ""
    # Username администратора (без @) для контакта в меню оплаты
    admin_username: str = ""

    wb_request_interval: float = 1.0
    ozon_request_interval: float = 1.0
    parser_concurrency: int = 5
    ssl_verify: bool = True
    http_proxy: str = ""  # http://login:pass@host:port — для обхода гео-блокировок
    http_retries: int = 3

    track_interval_min: int = 30

    admin_ids: str = ""

    ozon_client_id: str = ""
    ozon_api_key: str = ""
    wb_api_key: str = ""

    @property
    def admins(self) -> list[int]:
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip()]

    def ensure_data_dir(self) -> None:
        db_path = self.database_url.split("///")[-1]
        if db_path and not db_path.startswith(("http", "postgres")):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_data_dir()
