from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from psycopg.errors import FeatureNotSupported

from tubesiphon.storage import db


class DatabaseConfigTest(unittest.TestCase):
    def test_load_database_config_prefers_tubesiphon_database_url(self) -> None:
        config = db.load_database_config(
            {
                "DATABASE_URL": "postgresql://generic/example",
                "TUBESIPHON_DATABASE_URL": "postgresql://specific/example",
            }
        )

        self.assertEqual(config.url, "postgresql://specific/example")

    def test_load_database_config_rejects_missing_database_url(self) -> None:
        with self.assertRaisesRegex(
            db.DatabaseConfigurationError,
            "Set TUBESIPHON_DATABASE_URL or DATABASE_URL",
        ):
            db.load_database_config({})

    def test_create_connection_pool_uses_loaded_config(self) -> None:
        with patch.object(db, "ConnectionPool") as connection_pool:
            pool = db.create_connection_pool(
                db.DatabaseConfig(url="postgresql://db/example")
            )

        self.assertIs(pool, connection_pool.return_value)
        connection_pool.assert_called_once_with(
            conninfo="postgresql://db/example",
            min_size=1,
            max_size=4,
            open=True,
        )


class InitializeDatabaseTest(unittest.TestCase):
    def test_initialize_database_executes_schema_sql_and_commits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            schema_path = Path(tmp) / "schema.sql"
            schema_path.write_text("CREATE TABLE example(id integer);", encoding="utf-8")
            connection = _FakeConnection()
            pool = _FakePool(connection)

            with patch.object(db, "create_connection_pool", return_value=pool):
                db.initialize_database(
                    db.DatabaseConfig(url="postgresql://db/example"),
                    schema_path=schema_path,
                )

        self.assertEqual(
            connection.executed_sql,
            ["CREATE TABLE example(id integer);"],
        )
        self.assertTrue(connection.committed)
        self.assertTrue(pool.closed)

    def test_initialize_database_rejects_missing_schema_file(self) -> None:
        missing_path = Path("/tmp/tubesiphon-missing-schema.sql")

        with self.assertRaisesRegex(
            db.SchemaNotFoundError,
            "Schema file not found",
        ):
            db.initialize_database(
                db.DatabaseConfig(url="postgresql://db/example"),
                schema_path=missing_path,
            )

    def test_initialize_database_wraps_connection_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            schema_path = Path(tmp) / "schema.sql"
            schema_path.write_text("SELECT 1;", encoding="utf-8")
            pool = _FailingPool(RuntimeError("connection refused"))

            with patch.object(db, "create_connection_pool", return_value=pool):
                with self.assertRaisesRegex(
                    db.DatabaseConnectionError,
                    "Failed to connect to PostgreSQL",
                ):
                    db.initialize_database(
                        db.DatabaseConfig(url="postgresql://db/example"),
                        schema_path=schema_path,
                    )

    def test_initialize_database_reports_schema_execution_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            schema_path = Path(tmp) / "schema.sql"
            schema_path.write_text("CREATE EXTENSION vector;", encoding="utf-8")
            connection = _FakeConnection(
                execute_error=FeatureNotSupported('extension "vector" is not available')
            )
            pool = _FakePool(connection)

            with patch.object(db, "create_connection_pool", return_value=pool):
                with self.assertRaisesRegex(
                    db.DatabaseInitializationError,
                    'Failed to initialize database schema: extension "vector" is not available',
                ):
                    db.initialize_database(
                        db.DatabaseConfig(url="postgresql://db/example"),
                        schema_path=schema_path,
                    )


class _FakeConnection:
    def __init__(self, execute_error: Exception | None = None) -> None:
        self._execute_error = execute_error
        self.executed_sql: list[str] = []
        self.committed = False

    def execute(self, sql: str) -> None:
        if self._execute_error is not None:
            raise self._execute_error
        self.executed_sql.append(sql)

    def commit(self) -> None:
        self.committed = True


class _FakePool:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection
        self.closed = False

    def __enter__(self) -> _FakePool:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.closed = True

    def connection(self) -> _ConnectionContext:
        return _ConnectionContext(self._connection)


class _ConnectionContext:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    def __enter__(self) -> _FakeConnection:
        return self._connection

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _FailingPool:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def __enter__(self) -> _FailingPool:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def connection(self) -> None:
        raise self._error
