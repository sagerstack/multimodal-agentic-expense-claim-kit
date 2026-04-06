"""Shared async database session factory for web routers."""

from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agentic_claims.core.config import getSettings


@asynccontextmanager
async def getAsyncSession():
    """Async context manager providing a SQLAlchemy AsyncSession.

    Creates a per-request engine and session. Disposes the engine on exit.
    Usage:
        async with getAsyncSession() as session:
            result = await session.execute(...)
    """
    settings = getSettings()
    engine = create_async_engine(settings.postgres_dsn_async, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()
