from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

db_url = settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
engine = create_engine(db_url, connect_args=connect_args, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.db import models  # noqa: F401  (register mappers)

    if settings.environment != "production":
        Base.metadata.create_all(bind=engine)
    else:
        from sqlalchemy import text
        with engine.connect() as conn:
            if conn.execute(text("select version_num from alembic_version")).scalar() != "0001":
                raise RuntimeError("Database migration required: alembic upgrade head")
