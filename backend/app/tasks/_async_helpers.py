"""Async helpers for Celery tasks.

`asyncio.run(coro)` opens and closes a fresh event loop per call, but the
global SQLAlchemy `async_session_factory` keeps an asyncpg connection pool
attached to whichever loop touched it first. The next Celery task lands on
a new loop and reuses dead connections, raising
`RuntimeError: Event loop is closed`.

`run_in_task_loop` builds a fresh event loop AND a fresh `AsyncEngine` per
task. The engine is disposed before the loop closes, so no cross-task
contamination is possible.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

T = TypeVar("T")

TaskSessionFactory = async_sessionmaker[AsyncSession]


def run_in_task_loop(coro_factory: Callable[[TaskSessionFactory], Awaitable[T]]) -> T:
    """Run `coro_factory(session_factory)` in a fresh loop + fresh engine.

    Each Celery task gets its own asyncpg pool that lives and dies inside
    the task's event loop, avoiding `RuntimeError: Event loop is closed`.

    Usage from a Celery task::

        async def _do_work_async(session_factory):
            async with session_factory() as db:
                ...

        @celery.task
        def do_work():
            run_in_task_loop(_do_work_async)
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={
            "command_timeout": 60,
            "statement_cache_size": 0,
        },
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        return loop.run_until_complete(coro_factory(session_factory))
    finally:
        try:
            loop.run_until_complete(engine.dispose())
        except Exception:
            pass
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
