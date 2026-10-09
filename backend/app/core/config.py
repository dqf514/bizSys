"""应用配置（pydantic-settings，读 .env / 环境变量）。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "dev"
    debug: bool = False

    db_url: str = "mysql+pymysql://root:bizsys123@127.0.0.1:3307/bizsys?charset=utf8mb4"
    redis_url: str = "redis://127.0.0.1:6379/0"

    jwt_secret: str = "dev-secret-change-me-0123456789abcdef"  # 仅开发默认值，生产必须经 JWT_SECRET 环境变量更换
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    upload_dir: str = "./uploads"
    upload_max_mb: int = 50
    upload_allowed_ext: str = "pdf,doc,docx,xls,xlsx,jpg,jpeg,png,zip"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def upload_ext_set(self) -> set[str]:
        return {e.strip().lower() for e in self.upload_allowed_ext.split(",") if e.strip()}

    @property
    def is_dev(self) -> bool:
        return self.env in ("dev", "sit", "test")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
