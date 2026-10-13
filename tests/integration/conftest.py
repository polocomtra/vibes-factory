"""Isolated PostgreSQL fixtures for runtime persistence integration tests."""

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.app.db import Base


@pytest_asyncio.fixture(scope="session")
async def runtime_test_session_factory() -> AsyncIterator[
    async_sessionmaker[AsyncSession]
]:
    database_url = os.environ.get("VF_TEST_DATABASE_URL")
    if not database_url:
        if os.environ.get("CI"):
            raise RuntimeError("VF_TEST_DATABASE_URL is required in CI.")
        pytest.skip("Set VF_TEST_DATABASE_URL to run PostgreSQL integration tests.")
    database_name = make_url(database_url).database
    if not database_name or not database_name.endswith("_test"):
        raise RuntimeError(
            "Runtime integration tests require a database ending in _test."
        )

    engine = create_async_engine(database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def runtime_test_session(
    runtime_test_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with runtime_test_session_factory() as setup_session:
        table_names = [
            table.name
            for table in Base.metadata.sorted_tables
            if table.name != "alembic_version"
        ]
        quoted = ", ".join(f'"{name}"' for name in table_names)
        await setup_session.execute(text(f"TRUNCATE TABLE {quoted} CASCADE"))
        await setup_session.commit()

    async with runtime_test_session_factory() as session:
        yield session
        await session.rollback()
