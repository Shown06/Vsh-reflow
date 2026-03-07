"""
Vsh-reflow - データベース接続管理
SQLAlchemy asyncioベースのPostgreSQL接続管理。
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.config import settings


from sqlalchemy.pool import NullPool

engine = create_async_engine(
    settings.database.url,
    echo=(settings.environment == "development"),
    poolclass=NullPool,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy宣言的ベースクラス"""
    pass


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """非同期DBセッションを取得するコンテキストマネージャー"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """データベーステーブルを初期化"""
    async with engine.begin() as conn:
        from src.models import (  # noqa: F401
            Task,
            ApprovalRequest,
            AuditLog,
            CostRecord,
            AgentMessage,
            MeetingRecord,
        )
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """データベース接続をクローズ"""
    await engine.dispose()
