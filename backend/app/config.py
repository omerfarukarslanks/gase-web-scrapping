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
    ANALYSIS_TEXT_CHAR_LIMIT: int = 10000
    VISUAL_ASSET_MAX_PER_TOPIC: int = 3
    VISUAL_ASSET_FETCH_TIMEOUT_SECONDS: float = 5.0

    # TTS
    ELEVENLABS_API_KEY: str = ""
    TTS_AUDIO_DIR: str = "static/audio"

    # Image generation (Stable Diffusion XL)
    SDXL_BASE_URL: str = "http://192.168.1.103:8000"
    IMAGE_OUTPUT_DIR: str = "static/images"

    # Video renderer service
    RENDERER_URL: str = "http://renderer:3001"
    VIDEO_OUTPUT_DIR: str = "static/videos"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:80"]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
