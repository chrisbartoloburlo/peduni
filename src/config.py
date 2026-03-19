from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_token: str
    database_url: str
    encryption_key: str
    google_client_id: str
    google_client_secret: str
    base_url: str

    model_config = {"env_file": ".env"}


settings = Settings()
