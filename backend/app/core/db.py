"""SQLAlchemy Engine / Session（同步驱动 + FastAPI 线程池，见 ADR-0001）。"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _ensure_utf8mb4(url: str) -> str:
    """历史教训：连接缺 charset 时 pymysql 默认 latin1，中文双编码落库成 mojibake。"""
    if "charset=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}charset=utf8mb4"
    return url


engine = create_engine(
    _ensure_utf8mb4(settings.db_url),
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=30,
    pool_recycle=3600,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
