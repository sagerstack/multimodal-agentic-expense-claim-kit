"""Configuration management using pydantic-settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env.local", case_sensitive=False)

    # Postgres configuration
    postgres_host: str = Field(..., description="PostgreSQL host")
    postgres_port: int = Field(..., description="PostgreSQL port")
    postgres_db: str = Field(..., description="PostgreSQL database name")
    postgres_user: str = Field(..., description="PostgreSQL user")
    postgres_password: str = Field(..., description="PostgreSQL password")

    # Chainlit configuration
    chainlit_host: str = Field(..., description="Chainlit host")
    chainlit_port: int = Field(..., description="Chainlit port")

    # Application environment
    app_env: str = Field(..., description="Application environment (local, prod)")

    @property
    def postgres_dsn(self) -> str:
        """Build PostgreSQL connection string from individual fields."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


def getSettings() -> Settings:
    """Create and return a Settings instance."""
    return Settings()
