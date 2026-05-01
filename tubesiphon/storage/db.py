"""PostgreSQL connection and schema initialization helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from psycopg import Error as PsycopgError
from psycopg_pool import ConnectionPool, PoolTimeout


DATABASE_ENV_VARS = ("TUBESIPHON_DATABASE_URL", "DATABASE_URL")
DEFAULT_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class TubeSiphonDatabaseError(Exception):
    """Base class for database errors suitable for CLI display."""


class DatabaseConfigurationError(TubeSiphonDatabaseError):
    """Raised when database connection settings are missing or invalid."""


class DatabaseConnectionError(TubeSiphonDatabaseError):
    """Raised when PostgreSQL cannot be reached or used."""


class DatabaseInitializationError(TubeSiphonDatabaseError):
    """Raised when the schema SQL fails during execution."""


class SchemaNotFoundError(TubeSiphonDatabaseError):
    """Raised when the schema file cannot be found."""


@dataclass(frozen=True)
class DatabaseConfig:
    """Database connection settings."""

    url: str
    min_size: int = 1
    max_size: int = 4


def load_database_config(env: Mapping[str, str] | None = None) -> DatabaseConfig:
    """Load PostgreSQL connection settings from the process environment."""

    source = os.environ if env is None else env
    for name in DATABASE_ENV_VARS:
        value = source.get(name, "").strip()
        if value:
            return DatabaseConfig(url=value)

    raise DatabaseConfigurationError(
        "Database is not configured. Set TUBESIPHON_DATABASE_URL or DATABASE_URL "
        "to a PostgreSQL connection string."
    )


def create_connection_pool(config: DatabaseConfig | str | None = None) -> ConnectionPool:
    """Create a psycopg connection pool for TubeSiphon."""

    database_config = _coerce_database_config(config)
    return ConnectionPool(
        conninfo=database_config.url,
        min_size=database_config.min_size,
        max_size=database_config.max_size,
        open=True,
    )


def initialize_database(
    config: DatabaseConfig | str | None = None,
    *,
    schema_path: Path | None = None,
) -> None:
    """Execute the TubeSiphon schema SQL against PostgreSQL."""

    schema_sql = _read_schema(schema_path or DEFAULT_SCHEMA_PATH)

    try:
        with create_connection_pool(config) as pool:
            try:
                with pool.connection() as connection:
                    try:
                        connection.execute(schema_sql)
                        connection.commit()
                    except (PsycopgError, RuntimeError) as exc:
                        raise DatabaseInitializationError(
                            "Failed to initialize database schema: "
                            f"{_format_database_error(exc)}"
                        ) from exc
            except DatabaseInitializationError:
                raise
            except (PsycopgError, PoolTimeout, OSError, RuntimeError) as exc:
                raise DatabaseConnectionError(
                    "Failed to connect to PostgreSQL. Check "
                    "TUBESIPHON_DATABASE_URL or DATABASE_URL and verify the "
                    "database server is reachable."
                ) from exc
    except TubeSiphonDatabaseError:
        raise
    except (PsycopgError, PoolTimeout, OSError, RuntimeError) as exc:
        raise DatabaseConnectionError(
            "Failed to connect to PostgreSQL. Check TUBESIPHON_DATABASE_URL "
            "or DATABASE_URL and verify the database server is reachable."
        ) from exc


def _coerce_database_config(config: DatabaseConfig | str | None) -> DatabaseConfig:
    if config is None:
        return load_database_config()
    if isinstance(config, DatabaseConfig):
        if config.url.strip():
            return config
        raise DatabaseConfigurationError(
            "Database is not configured. Set TUBESIPHON_DATABASE_URL or "
            "DATABASE_URL to a PostgreSQL connection string."
        )
    if config.strip():
        return DatabaseConfig(url=config.strip())
    raise DatabaseConfigurationError(
        "Database is not configured. Set TUBESIPHON_DATABASE_URL or DATABASE_URL "
        "to a PostgreSQL connection string."
    )


def _read_schema(schema_path: Path) -> str:
    if not schema_path.exists():
        raise SchemaNotFoundError(f"Schema file not found: {schema_path}")
    if not schema_path.is_file():
        raise SchemaNotFoundError(f"Schema path is not a file: {schema_path}")
    return schema_path.read_text(encoding="utf-8")


def _format_database_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__
