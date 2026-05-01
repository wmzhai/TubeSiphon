from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from tubesiphon.ingest import subtitle
from tubesiphon.ingest.parser import TranscriptCue


KNOWN_VIDEO_ID = "-b9Jvb3Fyqc"
KNOWN_VIDEO_URL = f"https://www.youtube.com/watch?v={KNOWN_VIDEO_ID}"


class SubtitleSelectionTest(unittest.TestCase):
    def test_select_subtitle_track_prefers_manual_subtitles(self) -> None:
        payload = {
            "id": KNOWN_VIDEO_ID,
            "subtitles": {
                "en": [{"ext": "vtt", "url": "https://video.google.com/manual"}],
            },
            "automatic_captions": {
                "en": [{"ext": "vtt", "url": "https://video.google.com/auto"}],
            },
        }

        track = subtitle.select_subtitle_track(payload)

        self.assertEqual(track.language, "en")
        self.assertEqual(track.source, "manual")

    def test_select_subtitle_track_falls_back_to_automatic_captions(self) -> None:
        payload = {
            "id": KNOWN_VIDEO_ID,
            "subtitles": {},
            "automatic_captions": {
                "en": [{"ext": "vtt", "url": "https://video.google.com/auto"}],
            },
        }

        track = subtitle.select_subtitle_track(payload)

        self.assertEqual(track.language, "en")
        self.assertEqual(track.source, "automatic")

    def test_fetch_video_subtitle_retries_automatic_when_manual_download_fails(
        self,
    ) -> None:
        payload = {
            "id": KNOWN_VIDEO_ID,
            "subtitles": {
                "en": [{"ext": "vtt", "url": "https://video.google.com/manual"}],
            },
            "automatic_captions": {
                "en": [{"ext": "vtt", "url": "https://video.google.com/auto"}],
            },
        }
        calls: list[list[str]] = []

        def run(command: list[str], **_kwargs: object) -> _CompletedProcess:
            calls.append(command)
            if "-J" in command:
                return _CompletedProcess(returncode=0, stdout=json.dumps(payload), stderr="")
            if "--write-subs" in command:
                return _CompletedProcess(returncode=1, stdout="", stderr="manual failed")

            output_template = Path(command[command.index("-o") + 1])
            output_template.parent.mkdir(parents=True, exist_ok=True)
            (output_template.parent / f"{KNOWN_VIDEO_ID}.en.vtt").write_text(
                "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nGet Cash Ready\n",
                encoding="utf-8",
            )
            return _CompletedProcess(returncode=0, stdout="", stderr="")

        with patch.object(subtitle.subprocess, "run", side_effect=run):
            with self.assertLogs("tubesiphon.ingest.subtitle", level="WARNING") as logs:
                downloaded = subtitle.fetch_video_subtitle(KNOWN_VIDEO_ID)

        self.assertEqual(downloaded.video_id, KNOWN_VIDEO_ID)
        self.assertEqual(downloaded.source, "automatic")
        self.assertEqual(downloaded.language, "en")
        self.assertIn("Get Cash Ready", downloaded.content)
        self.assertEqual(calls[0][:3], ["yt-dlp", "-J", "--skip-download"])
        self.assertEqual(calls[0][-1], KNOWN_VIDEO_URL)
        self.assertIn("--write-subs", calls[1])
        self.assertIn("--write-auto-subs", calls[2])
        self.assertIn("manual failed", "\n".join(logs.output))


class VideoTranscriptIngestTest(unittest.TestCase):
    def test_ingest_video_upserts_transcripts_idempotently(self) -> None:
        connection = _RecordingConnection()
        pool = _RecordingPool(connection)
        downloaded = subtitle.DownloadedSubtitle(
            video_id=KNOWN_VIDEO_ID,
            language="en",
            source="manual",
            content="WEBVTT",
        )
        cues = [
            TranscriptCue(start_time=0.0, text="Trump May Crash the Market"),
            TranscriptCue(start_time=2.5, text="Get Cash Ready"),
        ]

        with patch.object(subtitle, "fetch_video_subtitle", return_value=downloaded):
            with patch.object(subtitle, "parse_vtt", return_value=cues):
                with patch.object(subtitle, "create_connection_pool", return_value=pool):
                    result = subtitle.ingest_video(KNOWN_VIDEO_ID)

        self.assertEqual(result.video_id, KNOWN_VIDEO_ID)
        self.assertEqual(result.transcript_count, 2)
        self.assertEqual(result.subtitle_source, "manual")
        self.assertTrue(pool.closed)
        self.assertTrue(connection.committed)
        executed_sql = "\n".join(sql for sql, _params in connection.executed)
        self.assertIn("INSERT INTO transcripts", executed_sql)
        self.assertIn("ON CONFLICT (video_id, start_time) DO UPDATE", executed_sql)
        self.assertEqual(
            connection.executed[0][1],
            {
                "video_id": KNOWN_VIDEO_ID,
                "start_time": 0.0,
                "text": "Trump May Crash the Market",
            },
        )
        self.assertEqual(connection.executed[1][1]["start_time"], 2.5)


class SubtitleIngestCliTest(unittest.TestCase):
    def test_ingest_cli_invokes_subtitle_ingest(self) -> None:
        from tubesiphon.cli import main as cli

        stdout = io.StringIO()
        result = subtitle.VideoTranscriptIngestResult(
            video_id=KNOWN_VIDEO_ID,
            transcript_count=2,
            subtitle_language="en",
            subtitle_source="manual",
        )

        with patch.object(cli, "ingest_video", return_value=result) as ingest_video:
            with contextlib.redirect_stdout(stdout):
                exit_code = cli.main(["ingest", KNOWN_VIDEO_ID])

        self.assertEqual(exit_code, 0)
        ingest_video.assert_called_once_with(KNOWN_VIDEO_ID)
        self.assertIn(f"Ingested subtitles for {KNOWN_VIDEO_ID}", stdout.getvalue())
        self.assertIn("2 transcript cues", stdout.getvalue())

    def test_ingest_cli_reports_failures_without_traceback(self) -> None:
        from tubesiphon.cli import main as cli

        stderr = io.StringIO()

        with patch.object(
            cli,
            "ingest_video",
            side_effect=subtitle.SubtitleIngestError("subtitle unavailable"),
        ):
            with contextlib.redirect_stderr(stderr):
                exit_code = cli.main(["ingest", KNOWN_VIDEO_ID])

        self.assertEqual(exit_code, 1)
        message = stderr.getvalue()
        self.assertIn("error: subtitle unavailable", message)
        self.assertNotIn("Traceback", message)


class _CompletedProcess:
    def __init__(self, *, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _RecordingConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, dict[str, object]]] = []
        self.committed = False

    def execute(self, sql: str, params: dict[str, object]) -> None:
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
