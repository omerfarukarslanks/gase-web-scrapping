from pydantic_settings import BaseSettings


class Settings(BaseSettings):
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
    DEFAULT_RATE_LIMIT_RPM: int = 10
    USER_AGENT: str = "GaseNewsScraper/1.0"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:80"]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
