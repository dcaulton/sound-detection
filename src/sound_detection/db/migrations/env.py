import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import create_engine, engine_from_config, pool
from sqlmodel import SQLModel

config = context.config

# Safe logging config (won't crash if sections are missing)
if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except Exception:
        pass

# Import your models so autogenerate can see the tables
from sound_detection.db.models import SQLModel
target_metadata = SQLModel.metadata

# Override sqlalchemy.url from environment if set (for docker dev + testcontainers)
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url")

    # Force modern psycopg driver (your project uses psycopg[binary], not psycopg2)
    if url and url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)

    connectable = create_engine(
        url, # type: ignore[arg-type]
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
