from __future__ import annotations

import contextlib
import io
import os
import unittest
from unittest.mock import patch

from tubesiphon.cli.main import build_parser, main


class DatabaseCliTest(unittest.TestCase):
    def test_top_level_help_lists_db_command(self) -> None:
        help_text = build_parser().format_help()

        self.assertIn("db", help_text)

    def test_db_help_lists_init_command(self) -> None:
        stdout = io.StringIO()

        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stdout(stdout):
                main(["db", "--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("init", stdout.getvalue())

    def test_db_init_reports_missing_config_without_traceback(self) -> None:
        stderr = io.StringIO()

        with patch.dict(os.environ, {}, clear=True):
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["db", "init"])

        self.assertEqual(exit_code, 1)
        message = stderr.getvalue()
        self.assertIn("Database is not configured", message)
        self.assertIn("TUBESIPHON_DATABASE_URL", message)
        self.assertNotIn("Traceback", message)

    def test_db_init_calls_initializer(self) -> None:
        stdout = io.StringIO()

        with patch("tubesiphon.cli.main.initialize_database") as initialize_database:
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["db", "init"])

        self.assertEqual(exit_code, 0)
        initialize_database.assert_called_once_with()
        self.assertIn("Database schema initialized", stdout.getvalue())
