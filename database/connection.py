from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS
from .models import Base

class DatabaseManager:
    _instance: Optional['DatabaseManager'] = None 
    _engine = None
    _async_session_maker = None

    def __new__(cls) -> 'DatabaseManager':
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance

    async def init_db(self) -> None:
        database_url = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

        self._engine = create_async_engine(
            database_url,
            echo=False,
        )

        self._async_session_maker = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._async_session_maker = None

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        if self._async_session_maker is None:
            raise ValueError("Database is not initialized. Call init_db() first.")
            
        session = self._async_session_maker()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

db_manager = DatabaseManager()