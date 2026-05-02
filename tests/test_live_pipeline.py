from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.conftest import DATA_DIR, EXPECTED_CHANNEL_ID, KNOWN_VIDEO_ID, LIVE_CHANNEL_URL
from tubesiphon.cli import main as cli


@pytest.fixture(scope="session")
def live_pipeline_output(clean_data_dir: Path) -> Path:
    sync_exit_code = cli.main(["sync", LIVE_CHANNEL_URL])
    assert sync_exit_code == 0

    channel_dir = clean_data_dir / EXPECTED_CHANNEL_ID
    assert channel_dir.exists()
    assert not list((channel_dir / "videos").glob("*/transcript.yaml"))

    ingest_exit_code = cli.main(
        ["ingest", EXPECTED_CHANNEL_ID, "--limit", "5", "--workers", "2"]
    )
    assert ingest_exit_code == 0
    return channel_dir


def test_live_sync_writes_real_channel_list_only(live_pipeline_output: Path) -> None:
    channel_dir = live_pipeline_output

    channel_yaml = yaml.safe_load(
        (channel_dir / "channel.yaml").read_text(encoding="utf-8")
    )
    videos_yaml = yaml.safe_load(
        (channel_dir / "videos.yaml").read_text(encoding="utf-8")
    )
    failures_yaml = yaml.safe_load(
        (channel_dir / "failures.yaml").read_text(encoding="utf-8")
    )

    assert channel_yaml["channel_id"] == EXPECTED_CHANNEL_ID
    assert channel_yaml["name"]
    assert videos_yaml["channel_id"] == EXPECTED_CHANNEL_ID
    assert len(videos_yaml["videos"]) >= 5
    assert videos_yaml["videos"][0]["video_id"] == KNOWN_VIDEO_ID
    assert failures_yaml["channel_id"] == EXPECTED_CHANNEL_ID


def test_live_ingest_writes_first_five_real_transcripts(
    live_pipeline_output: Path,
) -> None:
    videos_yaml = yaml.safe_load(
        (live_pipeline_output / "videos.yaml").read_text(encoding="utf-8")
    )
    first_five_ids = [video["video_id"] for video in videos_yaml["videos"][:5]]
    failures_yaml = yaml.safe_load(
        (live_pipeline_output / "failures.yaml").read_text(encoding="utf-8")
    )
    failed_ids = {failure["video_id"] for failure in failures_yaml["failures"]}

    assert len(first_five_ids) == 5
    assert KNOWN_VIDEO_ID in first_five_ids
    assert not failed_ids

    for video_id in first_five_ids:
        video_dir = live_pipeline_output / "videos" / video_id
        metadata_yaml = yaml.safe_load(
            (video_dir / "metadata.yaml").read_text(encoding="utf-8")
        )
        transcript_yaml = yaml.safe_load(
            (video_dir / "transcript.yaml").read_text(encoding="utf-8")
        )
        transcript_md = (video_dir / "transcript.md").read_text(encoding="utf-8")
        transcript_vtt = (video_dir / "transcript.vtt").read_text(encoding="utf-8")

        assert metadata_yaml["video_id"] == video_id
        assert metadata_yaml["channel_id"] == EXPECTED_CHANNEL_ID
        assert metadata_yaml["title"]
        assert transcript_yaml["video_id"] == video_id
        assert transcript_yaml["cues"]
        assert transcript_md.startswith(f"# {metadata_yaml['title']}\n")
        assert transcript_vtt.startswith("WEBVTT")


def test_live_results_remain_in_project_data(live_pipeline_output: Path) -> None:
    assert live_pipeline_output == DATA_DIR / EXPECTED_CHANNEL_ID
    assert (live_pipeline_output / "videos.yaml").exists()
