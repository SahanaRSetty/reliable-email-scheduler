import os

from dotenv import load_dotenv


load_dotenv()


class Settings:
    database_url: str = os.getenv("DATABASE_URL", "")

    redis_url: str = os.getenv(
        "REDIS_URL",
        "redis://localhost:6379/0",
    )

    MAX_EMAIL_ATTEMPTS: int = 3

    PROCESSING_TIMEOUT_SECONDS: int = 60

    RETRY_BASE_DELAY_SECONDS: int = int(
        os.getenv("RETRY_BASE_DELAY_SECONDS", "10")
    )

    RETRY_MAX_DELAY_SECONDS: int = int(
        os.getenv("RETRY_MAX_DELAY_SECONDS", "300")
    )

    # ---------------------------------------------------------
    # Google OAuth
    # ---------------------------------------------------------

    GOOGLE_CLIENT_ID: str = os.getenv(
        "GOOGLE_CLIENT_ID",
        ""
    )

    GOOGLE_CLIENT_SECRET: str = os.getenv(
        "GOOGLE_CLIENT_SECRET",
        ""
    )

    GOOGLE_REDIRECT_URI: str = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )

    # ---------------------------------------------------------
    # Session
    # ---------------------------------------------------------

    SESSION_SECRET_KEY: str = os.getenv(
        "SESSION_SECRET_KEY",
        "dev-secret-change-this",
    )


settings = Settings()