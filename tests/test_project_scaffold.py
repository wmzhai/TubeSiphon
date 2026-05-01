from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProjectScaffoldTest(unittest.TestCase):
    def test_project_declares_core_dependencies(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        dependencies = project["project"]["dependencies"]

        expected = {
            "yt-dlp",
            "psycopg[binary]",
            "psycopg-pool",
            "pgvector",
            "sentence-transformers",
            "tqdm",
        }
        declared = {
            dependency.split(">=", maxsplit=1)[0] for dependency in dependencies
        }
        self.assertLessEqual(expected, declared)

    def test_schema_defines_required_tables_constraints_and_indexes(self) -> None:
        schema_path = ROOT / "tubesiphon" / "storage" / "schema.sql"
        self.assertTrue(schema_path.exists(), "schema.sql must exist")
        schema = schema_path.read_text(encoding="utf-8")

        for table in ("channels", "videos", "transcripts", "chunks", "embeddings"):
            self.assertRegex(schema, rf"CREATE TABLE IF NOT EXISTS {table}\b")

        self.assertIn("CREATE EXTENSION IF NOT EXISTS vector", schema)
        self.assertIn("embedding vector(1536)", schema)
        self.assertIn("UNIQUE (url)", schema)
        self.assertIn("UNIQUE (video_id, start_time)", schema)
        self.assertIn("UNIQUE (video_id, chunk_index)", schema)
        self.assertRegex(schema, r"CREATE INDEX IF NOT EXISTS .*transcripts.*video_id")
        self.assertRegex(schema, r"CREATE INDEX IF NOT EXISTS .*chunks.*video_id")
        self.assertTrue(
            re.search(
                r"CREATE INDEX IF NOT EXISTS .*embeddings.*ivfflat.*vector_cosine_ops",
                schema,
                flags=re.DOTALL,
            )
        )
