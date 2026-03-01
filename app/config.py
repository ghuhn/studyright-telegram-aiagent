import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    telegram_bot_token: str
    groq_api_key: str
    email_address: str = ""
    email_app_password: str = ""
    email_imap_server: str = "imap.gmail.com"
    database_url: str = "sqlite:///./database.db"
    pinecone_api_key: str = ""
    pinecone_index_name: str = "ai-study-agent-db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
