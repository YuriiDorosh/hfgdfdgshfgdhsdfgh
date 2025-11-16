from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Single Proxy API"
    API_V1_STR: str = "/api/v1"

    # single upstream service
    UPSTREAM_BASE_URL: str

    # DB config
    DB_USER: str = "proxy"
    DB_PASSWORD: str = "proxy"
    DB_HOST: str = "db"
    DB_PORT: int = 5432
    DB_NAME: str = "proxy_db"

    # retry config
    PROXY_MAX_RETRIES: int = 5
    PROXY_RETRY_DELAY_SECONDS: float = 3.0

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    class Config:
        env_file = ".env"


settings = Settings()
