"""Configuration centralisée, lue depuis les variables d'environnement (.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg2://utilisateur:motdepasse@localhost:5432/maintenance"
    secret_key: str = "dev-secret-a-changer"
    algorithm: str = "HS256"
    access_token_minutes: int = 60
    reset_token_minutes: int = 30
    encryption_key: str = ""
    cors_origins: list[str] = ["http://localhost:5173"]
    frontend_url: str = "http://localhost:5173"

    ai_provider: str = "mock"          # mock | gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    ai_timeout_seconds: float = 30.0
    ai_max_context_chars: int = 12000
    claude_api_key: str = ""
    claude_model: str = "claude-sonnet-5-5"
    claude_max_tokens: int = 8000

    git_workdir: str = "./var/depots"
    git_timeout_seconds: int = 120
    
        # Second analyseur PHP (PHPStan). Commande sous forme de liste, ex. ["php", "C:/outils/phpstan.phar"].
    phpstan_commande: list[str] = ["phpstan"]
    phpstan_niveau: int = 5
    phpstan_timeout_secondes: int = 300
    phpstan_signaler_classes_inconnues: bool = False

    smtp_enabled: bool = False
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@example.org"

    echeance_jours_avant: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
