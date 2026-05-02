from __future__ import annotations

import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_project_uses_pytest_and_file_output_dependencies() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = {
        dependency.split(">=", maxsplit=1)[0].lower()
        for dependency in project["project"]["dependencies"]
    }

    assert {"yt-dlp", "pyyaml"} <= dependencies
    assert any(
        dependency.startswith("pytest")
        for dependency in project["dependency-groups"]["dev"]
    )
    assert not {
        "psycopg",
        "psycopg[binary]",
        "psycopg-pool",
        "pgvector",
        "sentence-transformers",
    } & dependencies


def test_docs_do_not_reference_database_storage() -> None:
    forbidden_patterns = [
        "PostgreSQL",
        "pgvector",
        "psycopg",
        "DATABASE_URL",
        "schema.sql",
        "UPSERT",
        "database",
    ]

    for path in [ROOT / "AGENTS.md", ROOT / "README.md", ROOT / "docs" / "SPEC.md"]:
        text = path.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            assert not re.search(re.escape(pattern), text, flags=re.IGNORECASE), (
                f"{path.relative_to(ROOT)} still mentions {pattern}"
            )


def test_repo_does_not_use_invented_youtube_fixture_data() -> None:
    disallowed_patterns = {
        r"\b" + "UC" + "example" + r"\b": "invented channel id",
        r"\b" + "Example " + "Channel" + r"\b": "invented channel name",
        r"https://www\.youtube\.com/" + "@" + "example" + r"\b": "invented channel URL",
        r"\b" + "video" + "-one" + r"\b": "invented video id",
        r"\b" + "video" + "-two" + r"\b": "invented video id",
    }
    scan_paths = [ROOT / "AGENTS.md", ROOT / "README.md", ROOT / "tests"]
    violations: list[str] = []

    for path in _iter_text_files(scan_paths):
        text = path.read_text(encoding="utf-8")
        for pattern, reason in disallowed_patterns.items():
            if re.search(pattern, text):
                violations.append(f"{path.relative_to(ROOT)} uses {reason}: {pattern}")

    assert violations == []


def _iter_text_files(paths: list[Path]) -> list[Path]:
    text_files: list[Path] = []
    for path in paths:
        if path.is_file():
            text_files.append(path)
            continue
        text_files.extend(
            child
            for child in path.rglob("*")
            if child.is_file()
            and "__pycache__" not in child.parts
            and child.suffix in {".md", ".py", ".json"}
        )
    return text_files
