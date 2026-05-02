from __future__ import annotations

import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LIVE_CHANNEL_URL = "https://www.youtube.com/@nicolasyounglive"
EXPECTED_CHANNEL_ID = "UCXUP_aBLQBNFgLjvnrMTHtw"
KNOWN_VIDEO_ID = "-b9Jvb3Fyqc"


@pytest.fixture(scope="session", autouse=True)
def clean_data_dir() -> Path:
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    DATA_DIR.mkdir(parents=True)
    return DATA_DIR
