from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.settings import settings
from core.models import Base

engine = create_async_engine(settings.database_url, echo=False, future=True)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Лёгкая миграция: новые колонки для существующих таблиц (SQLite не умеет ADD COLUMN через create_all)
_MIGRATIONS = {
    "users": {
        "ref_code": "VARCHAR(32)",
        "referred_by": "INTEGER",
    },
    "items": {
        "note": "VARCHAR(500)",
    },
}


async def _migrate_sqlite() -> None:
    async with engine.begin() as conn:
        for table, columns in _MIGRATIONS.items():
            result = await conn.execute(text(f"PRAGMA table_info({table})"))
            existing = {row[1] for row in result.fetchall()}
            for col, col_type in columns.items():
                if col not in existing:
                    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_sqlite()


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
