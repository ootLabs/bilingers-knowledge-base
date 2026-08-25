"""Alembic environment.

The database URL comes from `app.config`, not from alembic.ini, so the
application and the migrations can never disagree about which database they are
talking to and no credential is committed.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# `db/init/` owns health_probe, so it is deliberately absent from the metadata.
# Autogenerate reads anything absent as a table to drop, which would make the
# first generated revision delete the health probe. Hide it from comparison
# instead of relying on whoever reviews that diff to notice.
BOOTSTRAP_TABLES = {"health_probe"}


def include_name(name: str | None, type_: str, parent_names: dict) -> bool:
    if type_ == "table" and name in BOOTSTRAP_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it, for review or manual apply."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
