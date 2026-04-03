from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_TIMEZONE: str = "Europe/Istanbul"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/news_scraper"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True

    # Scraping
    SCRAPE_INTERVAL_MINUTES: int = 60
    ARTICLE_RETENTION_HOURS: int = 8
    DEFAULT_RATE_LIMIT_RPM: int = 10
    USER_AGENT: str = "GaseNewsScraper/1.0"
    GUARDIAN_API_KEY: str | None = None

    # Analysis
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "qwen3:14b"
    ANALYSIS_MIN_SHARED_SOURCES: int = 2
    ANALYSIS_MAX_ARTICLES_PER_RUN: int = 120
    ANALYSIS_MAX_ARTICLES_PER_SOURCE: int = 15
    ANALYSIS_TEXT_CHAR_LIMIT: int = 1200
    VISUAL_ASSET_MAX_PER_TOPIC: int = 3
    VISUAL_ASSET_FETCH_TIMEOUT_SECONDS: float = 5.0

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:80"]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
