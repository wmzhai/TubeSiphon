from __future__ import annotations

import contextlib
import copy
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from tubesiphon.ingest import channel


FIXTURES_DIR = Path(__file__).with_name("fixtures")
LIVE_CHANNEL_URL = "https://www.youtube.com/@nicolasyounglive"
LIVE_CHANNEL_LISTING_URL = f"{LIVE_CHANNEL_URL}/videos"
EXPECTED_CHANNEL_ID = "UCXUP_aBLQBNFgLjvnrMTHtw"
EXPECTED_CHANNEL_NAME = "尼可拉斯楊Live精"
KNOWN_VIDEO_IDS = [
    "-b9Jvb3Fyqc",
    "kMcWbh2F8z8",
    "n91eJ1MxG90",
    "dOcbr00N0Bc",
    "yhBKM3Mmn8U",
]


def _load_real_channel_fixture() -> dict[str, object]:
    fixture_path = FIXTURES_DIR / "nicolasyounglive_videos.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


class ChannelMetadataParsingTest(unittest.TestCase):
    def test_parse_channel_metadata_skips_invalid_video_entries(self) -> None:
        payload = copy.deepcopy(_load_real_channel_fixture())
        entries = payload["entries"]
        assert isinstance(entries, list)
        missing_id_entry = copy.deepcopy(entries[0])
        assert isinstance(missing_id_entry, dict)
        missing_id_entry.pop("id", None)
        missing_id_entry.pop("url", None)
        missing_id_entry.pop("webpage_url", None)
        corrupted_date_entry = copy.deepcopy(entries[0])
        assert isinstance(corrupted_date_entry, dict)
        corrupted_date_entry["upload_date"] = "April 2026"
        entries.insert(1, None)
        entries.insert(2, missing_id_entry)
        entries.insert(3, corrupted_date_entry)

        with self.assertLogs("tubesiphon.ingest.channel", level="WARNING") as logs:
            metadata = channel.parse_channel_metadata(
                payload,
                source_url=LIVE_CHANNEL_LISTING_URL,
            )

        self.assertEqual(metadata.channel_id, EXPECTED_CHANNEL_ID)
        self.assertEqual(metadata.name, EXPECTED_CHANNEL_NAME)
        self.assertEqual(
            [video.video_id for video in metadata.videos],
            KNOWN_VIDEO_IDS,
        )
        self.assertTrue(all(video.upload_date is None for video in metadata.videos))
        warning_text = "\n".join(logs.output)
        self.assertIn("Skipping video metadata", warning_text)
        self.assertIn("invalid upload_date", warning_text)
        self.assertIn("missing video id", warning_text)

    def test_parse_channel_metadata_rejects_missing_channel_id(self) -> None:
        payload = copy.deepcopy(_load_real_channel_fixture())
        for key in ("id", "channel_id", "uploader_id"):
            payload.pop(key, None)

        with self.assertRaisesRegex(channel.ChannelMetadataError, "channel id"):
            channel.parse_channel_metadata(
                payload,
                source_url=LIVE_CHANNEL_LISTING_URL,
            )


class YtDlpFetchTest(unittest.TestCase):
    def test_fetch_channel_metadata_invokes_yt_dlp_json_playlist_mode(self) -> None:
        fixture_json = json.dumps(_load_real_channel_fixture(), ensure_ascii=False)
        completed_process = _CompletedProcess(
            returncode=0,
            stdout=fixture_json,
            stderr="",
        )

        with patch.object(
            channel.subprocess,
            "run",
            return_value=completed_process,
        ) as run:
            payload = channel.fetch_channel_metadata(
                LIVE_CHANNEL_URL,
            )

        self.assertEqual(payload["id"], EXPECTED_CHANNEL_ID)
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["yt-dlp", "-J"])
        self.assertIn("--flat-playlist", command)
        self.assertIn("--ignore-errors", command)
        self.assertEqual(command[-1], LIVE_CHANNEL_LISTING_URL)

    def test_fetch_channel_metadata_keeps_explicit_video_listing_url(self) -> None:
        fixture_json = json.dumps(_load_real_channel_fixture(), ensure_ascii=False)
        completed_process = _CompletedProcess(
            returncode=0,
            stdout=fixture_json,
            stderr="",
        )

        with patch.object(
            channel.subprocess,
            "run",
            return_value=completed_process,
        ) as run:
            channel.fetch_channel_metadata(LIVE_CHANNEL_LISTING_URL)

        command = run.call_args.args[0]
        self.assertEqual(command[-1], LIVE_CHANNEL_LISTING_URL)

    def test_fetch_channel_metadata_logs_and_raises_on_yt_dlp_failure(self) -> None:
        completed_process = _CompletedProcess(
            returncode=1,
            stdout="",
            stderr="network unavailable",
        )

        with patch.object(
            channel.subprocess,
            "run",
            return_value=completed_process,
        ):
            with self.assertLogs("tubesiphon.ingest.channel", level="ERROR") as logs:
                with self.assertRaisesRegex(channel.YtDlpError, "network unavailable"):
                    channel.fetch_channel_metadata(LIVE_CHANNEL_URL)

        self.assertIn("yt-dlp failed", "\n".join(logs.output))


class ChannelSyncTest(unittest.TestCase):
    def test_sync_channel_upserts_channel_and_videos_idempotently(self) -> None:
        payload = _load_real_channel_fixture()
        connection = _RecordingConnection()
        pool = _RecordingPool(connection)

        with patch.object(channel, "fetch_channel_metadata", return_value=payload):
            with patch.object(channel, "create_connection_pool", return_value=pool):
                result = channel.sync_channel(LIVE_CHANNEL_URL)

        self.assertEqual(result.channel_id, EXPECTED_CHANNEL_ID)
        self.assertEqual(result.video_count, len(KNOWN_VIDEO_IDS))
        self.assertTrue(pool.closed)
        self.assertTrue(connection.committed)
        executed_sql = "\n".join(sql for sql, _params in connection.executed)
        self.assertIn("INSERT INTO channels", executed_sql)
        self.assertIn("ON CONFLICT (channel_id) DO UPDATE", executed_sql)
        self.assertIn("INSERT INTO videos", executed_sql)
        self.assertIn("ON CONFLICT (video_id) DO UPDATE", executed_sql)
        self.assertEqual(
            connection.executed[0][1],
            {
                "channel_id": EXPECTED_CHANNEL_ID,
                "url": "https://www.youtube.com/channel/UCXUP_aBLQBNFgLjvnrMTHtw",
                "name": EXPECTED_CHANNEL_NAME,
            },
        )
        self.assertEqual(connection.executed[1][1]["video_id"], KNOWN_VIDEO_IDS[0])
        self.assertEqual(connection.executed[-1][1]["video_id"], KNOWN_VIDEO_IDS[-1])


class ChannelSyncCliSmokeTest(unittest.TestCase):
    def test_sync_cli_invokes_channel_sync(self) -> None:
        from tubesiphon.cli import main as cli

        stdout = io.StringIO()
        result = channel.ChannelSyncResult(
            channel_id=EXPECTED_CHANNEL_ID,
            channel_name=EXPECTED_CHANNEL_NAME,
            video_count=len(KNOWN_VIDEO_IDS),
            skipped_video_count=1,
        )

        with patch.object(cli, "sync_channel", return_value=result) as sync_channel:
            with contextlib.redirect_stdout(stdout):
                exit_code = cli.main(["sync", LIVE_CHANNEL_URL])

        self.assertEqual(exit_code, 0)
        sync_channel.assert_called_once_with(LIVE_CHANNEL_URL)
        self.assertIn(f"Synchronized channel {EXPECTED_CHANNEL_ID}", stdout.getvalue())
        self.assertIn(f"{len(KNOWN_VIDEO_IDS)} videos", stdout.getvalue())
        self.assertIn("1 skipped", stdout.getvalue())

    def test_sync_cli_reports_failures_without_traceback(self) -> None:
        from tubesiphon.cli import main as cli

        stderr = io.StringIO()

        with patch.object(cli, "sync_channel", side_effect=channel.YtDlpError("boom")):
            with contextlib.redirect_stderr(stderr):
                exit_code = cli.main(["sync", LIVE_CHANNEL_URL])

        self.assertEqual(exit_code, 1)
        message = stderr.getvalue()
        self.assertIn("error: boom", message)
        self.assertNotIn("Traceback", message)


class _CompletedProcess:
    def __init__(self, *, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _RecordingConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, object]] = []
        self.committed = False

    def execute(self, sql: str, params: object | None = None) -> None:
        self.executed.append((sql, params))

    def commit(self) -> None:
        self.committed = True


class _RecordingPool:
    def __init__(self, connection: _RecordingConnection) -> None:
        self._connection = connection
        self.closed = False

    def __enter__(self) -> _RecordingPool:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.closed = True

    def connection(self) -> _ConnectionContext:
        return _ConnectionContext(self._connection)


class _ConnectionContext:
    def __init__(self, connection: _RecordingConnection) -> None:
        self._connection = connection

    def __enter__(self) -> _RecordingConnection:
        return self._connection

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None
