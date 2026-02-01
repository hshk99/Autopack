"""Alembic Environment Configuration

This file is the main configuration for Alembic migrations. It sets up the
migration environment, imports the database models, and provides a migration context.

For more information, see: https://alembic.sqlalchemy.org/en/latest/cookbook.html
"""

import asyncio

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from autopack import models  # noqa: F401 - Import to register models
from autopack.auth.models import APIKey, User  # noqa: F401 - Import to register auth models

# Import your Base and models
from autopack.config import get_database_url
from autopack.database import Base
from autopack.usage_recorder import (  # noqa: F401 - Import to register usage models
    DoctorUsageStats,
    LlmUsageEvent,
    TokenEfficiencyMetrics,
)

# Add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata

# Other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well. By skipping the Engine
    creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    config = context.config
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Run migrations synchronously."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    """Run migrations asynchronously."""
    config = context.config
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate a connection
    with the context.
    """
    config = context.config

    # Ensure database URL is set
    if not config.get_main_option("sqlalchemy.url"):
        config.set_main_option("sqlalchemy.url", get_database_url())

    # Try to use async migrations if the database URL suggests async
    db_url = get_database_url()
    if "+asyncpg" in db_url or "+aiosqlite" in db_url:
        asyncio.run(run_async_migrations())
    else:
        # Fallback to synchronous migrations
        connectable = engine_from_config(
            config.get_section(config.config_ini_section),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        with connectable.connect() as connection:
            do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
