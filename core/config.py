from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    currency: str = "INR"
    currency_symbol: str = "₹"
    database_url: str = "sqlite+aiosqlite:///./claimflow.db"
    qdrant_local_path: str = "./qdrant_storage"
    qdrant_collection: str = "comprehensive_motor_policies"
    auto_approve_threshold: float = 135000.0
    fraud_score_threshold: float = 0.65

    company_notify_email: str = "neuralrush82@gmail.com"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    company_webhook_url: str = ""
    send_customer_emails: bool = False


settings = Settings()