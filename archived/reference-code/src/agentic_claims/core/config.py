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

    # OpenRouter configuration
    openrouter_api_key: str = Field(..., description="OpenRouter API key")
    openrouter_model_llm: str = Field(..., description="OpenRouter LLM model name")
    openrouter_model_vlm: str = Field(..., description="OpenRouter VLM model name")
    openrouter_fallback_model_llm: str = Field(..., description="Fallback LLM model when primary returns 402")
    openrouter_fallback_model_vlm: str = Field(..., description="Fallback VLM model when primary returns 402")
    openrouter_base_url: str = Field(..., description="OpenRouter base URL")
    openrouter_max_retries: int = Field(..., description="OpenRouter max retry count")
    openrouter_retry_delay: float = Field(..., description="OpenRouter retry delay in seconds")
    openrouter_vlm_max_tokens: int = Field(..., description="Max tokens for VLM response generation")
    openrouter_llm_max_tokens: int = Field(..., description="Max tokens for LLM response generation")
    openrouter_llm_temperature: float = Field(..., description="LLM temperature (lower for reasoning models)")

    # Qdrant configuration
    qdrant_host: str = Field(..., description="Qdrant host")
    qdrant_port: int = Field(..., description="Qdrant port")

    # SMTP configuration (for email MCP server)
    smtp_host: str = Field(default="mailhog", description="SMTP host")
    smtp_port: int = Field(default=1025, description="SMTP port")
    smtp_user: str = Field(default="", description="SMTP username (optional)")
    smtp_password: str = Field(default="", description="SMTP password (optional)")

    # MCP Server URLs
    rag_mcp_url: str = Field(..., description="RAG MCP server URL")
    db_mcp_url: str = Field(..., description="Database MCP server URL")
    currency_mcp_url: str = Field(..., description="Currency conversion MCP server URL")
    email_mcp_url: str = Field(..., description="Email MCP server URL")

    # Image Quality Settings
    image_quality_threshold: float = Field(..., description="Laplacian variance threshold for blur detection")
    image_min_width: int = Field(..., description="Minimum image width in pixels")
    image_min_height: int = Field(..., description="Minimum image height in pixels")

    # VLM Confidence Threshold
    vlm_confidence_threshold: float = Field(..., description="Minimum VLM confidence before asking human")

    # Logging configuration
    log_level: str = Field(..., description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    log_file_path: str = Field(..., description="File path for log output (empty string means no file handler)")
    seq_url: str = Field(..., description="Seq dashboard URL for documentation/reference")
    seq_password: str = Field(..., description="Seq admin password")
    seq_ingestion_url: str = Field(..., description="Seq CLEF ingestion endpoint URL (Docker-internal, e.g. http://seq/api/events/raw)")

    @property
    def postgres_dsn(self) -> str:
        """Build PostgreSQL connection string from individual fields."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_dsn_async(self) -> str:
        """Build async PostgreSQL connection string for SQLAlchemy async engine."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def qdrant_url(self) -> str:
        """Build Qdrant URL from host and port."""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"


def getSettings() -> Settings:
    """Create and return a Settings instance."""
    return Settings()
