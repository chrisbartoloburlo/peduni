from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_token: str
    database_url: str
    encryption_key: str
    google_client_id: str
    google_client_secret: str
    base_url: str

    # Hosted AI — your key, used for paying users
    hosted_ai_provider: str = "openai"
    hosted_ai_model: str = "gpt-4o"
    hosted_ai_api_key: str | None = None

    # Free credits given to new "pay per use" users
    free_credits: int = 500

    model_config = {"env_file": ".env"}


settings = Settings()
