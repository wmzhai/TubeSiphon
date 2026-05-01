from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_PATHS = (
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    ROOT / "tests",
)
DISALLOWED_YOUTUBE_PLACEHOLDER_PATTERNS = {
    r"\b" + "UC" + "example" + r"\b": "invented channel id",
    r"\b" + "Example " + "Channel" + r"\b": "invented channel name",
    r"https://www\.youtube\.com/" + "@" + "example" + r"\b": "invented channel URL",
    r"\b" + "video" + "-one" + r"\b": "invented video id",
    r"\b" + "video" + "-two" + r"\b": "invented video id",
}


class YouTubeTestDataPolicyTest(unittest.TestCase):
    def test_repo_does_not_use_invented_youtube_fixture_data(self) -> None:
        violations: list[str] = []

        for path in _iter_text_files(SCAN_PATHS):
            text = path.read_text(encoding="utf-8")
            for pattern, reason in DISALLOWED_YOUTUBE_PLACEHOLDER_PATTERNS.items():
                if re.search(pattern, text):
                    violations.append(
                        f"{path.relative_to(ROOT)} uses {reason}: {pattern}"
                    )

        self.assertEqual(
            violations,
            [],
            "YouTube tests/docs must use the canonical real channel fixture "
            "instead of invented channel or video metadata.",
        )


def _iter_text_files(paths: tuple[Path, ...]) -> list[Path]:
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
