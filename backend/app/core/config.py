"""应用配置（pydantic-settings，读 .env / 环境变量）。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "dev"
    debug: bool = False
    # 应用版本号（语义化版本）：必须与 CHANGELOG.md 顶部版本、frontend/package.json、
    # backend/pyproject.toml 三处一致（tests/test_changelog.py 校验）
    app_version: str = "0.12.0"

    db_url: str = "mysql+pymysql://root:bizsys123@127.0.0.1:3307/bizsys?charset=utf8mb4"
    redis_url: str = "redis://127.0.0.1:6379/0"

    jwt_secret: str = "dev-secret-change-me-0123456789abcdef"  # 仅开发默认值，生产必须经 JWT_SECRET 环境变量更换
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    # 登录页「记住登录状态」两档口径：
    #   remember=true  → refresh token 30 天（跨浏览器重启免登录）
    #   remember=false → refresh token 12 小时（仅本次浏览器会话，前端存 sessionStorage）
    refresh_token_expire_days: int = 30
    refresh_token_expire_hours: int = 12

    upload_dir: str = "./uploads"
    upload_max_mb: int = 50
    upload_allowed_ext: str = "pdf,doc,docx,xls,xlsx,jpg,jpeg,png,zip"
    audit_anchor_dir: str = "./data/audit-anchor"  # 审计链锚点文件（DB 之外，可发现整链重写）
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    portal_token_expire_minutes: int = 720  # 门户 token（无刷新机制），默认 12 小时
    portal_base_url: str = ""  # 门户对外地址（访客通行二维码短链用）；留空则取请求来源
    portal_refresh_expire_days: int = 7  # 门户 refresh token 有效期（存 Redis）

    # 反向代理链（真实客户端 IP）：审计日志要记访问者的公网 IP，而不是 nginx / 网关容器 IP。
    # 详见 app/core/client_ip.py。
    trust_proxy_headers: bool = True  # 总开关；关掉则一律用 TCP 对端地址
    trusted_proxy_hops: int = 2  # 受控代理跳数（从 X-Forwarded-For 右侧往左数）；0 = 不信任代理头
    trusted_proxy_cidrs: str = ""  # 可选：显式受信任代理的 IP/CIDR 列表；填了则以网段判定（优先于跳数）

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
