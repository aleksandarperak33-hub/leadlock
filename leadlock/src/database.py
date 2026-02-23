"""
Async SQLAlchemy database engine and session management.
Uses asyncpg driver for PostgreSQL async connections.
CRITICAL: expire_on_commit=False prevents lazy-loading issues in async contexts.
"""
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

_engine = None
_async_session_factory = None


class Base(DeclarativeBase):
    pass


def _get_engine():
    global _engine
    if _engine is None:
        from src.config import get_settings
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            echo=settings.app_env == "development",
        )
    return _engine


def _get_session_factory():
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            _get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _async_session_factory


def async_session_factory() -> AsyncSession:
    """Get session factory for use in background workers (non-FastAPI context)."""
    return _get_session_factory()()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    session_factory = _get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.debug("Database session error, rolling back: %s", str(e))
            await session.rollback()
            raise
        finally:
            await session.close()
