"""Single-video subtitle download and transcript ingestion."""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from psycopg import Error as PsycopgError

from tubesiphon.ingest.parser import TranscriptCue, VttParseError, parse_vtt
from tubesiphon.storage.db import (
    DatabaseConfig,
    TubeSiphonDatabaseError,
    create_connection_pool,
)


LOGGER = logging.getLogger(__name__)
SubtitleSource = Literal["manual", "automatic"]
DEFAULT_LANGUAGE_PRIORITY = (
    "en",
    "en-US",
    "en-GB",
    "en-orig",
    "zh-Hant",
    "zh-Hans",
    "zh-TW",
    "zh-CN",
    "zh",
)


class SubtitleIngestError(Exception):
    """Base class for subtitle ingestion errors suitable for CLI display."""


class SubtitleDownloadError(SubtitleIngestError):
    """Raised when yt-dlp cannot download a usable subtitle file."""


class SubtitleSelectionError(SubtitleIngestError):
    """Raised when a video has no usable WebVTT subtitle tracks."""


class SubtitleParseError(SubtitleIngestError):
    """Raised when a downloaded subtitle file cannot be parsed."""


@dataclass(frozen=True)
class SubtitleTrack:
    """A chosen subtitle track from yt-dlp metadata."""

    language: str
    source: SubtitleSource


@dataclass(frozen=True)
class DownloadedSubtitle:
    """Downloaded WebVTT content and its source metadata."""

    video_id: str
    language: str
    source: SubtitleSource
    content: str


@dataclass(frozen=True)
class VideoTranscriptIngestResult:
    """Summary returned after ingesting one video's transcript cues."""

    video_id: str
    transcript_count: int
    subtitle_language: str
    subtitle_source: SubtitleSource


def select_subtitle_track(payload: Mapping[str, Any]) -> SubtitleTrack:
    """Select the best subtitle track, preferring manual subtitles."""

    track = _select_from_track_mapping(payload.get("subtitles"), source="manual")
    if track is not None:
        return track

    track = _select_from_track_mapping(
        payload.get("automatic_captions"),
        source="automatic",
    )
    if track is not None:
        return track

    raise SubtitleSelectionError("No manual or automatic WebVTT subtitles found")


def fetch_video_subtitle(
    video_id: str,
    *,
    yt_dlp_binary: str = "yt-dlp",
) -> DownloadedSubtitle:
    """Download one video's best WebVTT subtitle with manual-first fallback."""

    video_url = _coerce_video_url(video_id)
    payload = _fetch_video_metadata(video_url, yt_dlp_binary=yt_dlp_binary)
    resolved_video_id = str(payload.get("id") or video_id).strip()
    candidates = list(_iter_candidate_tracks(payload))
    if not candidates:
        message = f"No manual or automatic WebVTT subtitles found for {video_id}"
        LOGGER.error(message)
        raise SubtitleSelectionError(message)

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for track in candidates:
            try:
                content = _download_track(
                    video_url,
                    track,
                    output_dir=Path(tmpdir),
                    yt_dlp_binary=yt_dlp_binary,
                )
            except SubtitleDownloadError as exc:
                failures.append(f"{track.source} {track.language}: {exc}")
                LOGGER.warning(
                    "Subtitle download failed for video %s using %s %s: %s",
                    video_id,
                    track.source,
                    track.language,
                    exc,
                )
                continue

            return DownloadedSubtitle(
                video_id=resolved_video_id,
                language=track.language,
                source=track.source,
                content=content,
            )

    detail = "; ".join(failures) or "no subtitle candidates were attempted"
    message = f"Failed to download subtitles for {video_id}: {detail}"
    LOGGER.error(message)
    raise SubtitleDownloadError(message)


def ingest_video(
    video_id: str,
    *,
    config: DatabaseConfig | str | None = None,
) -> VideoTranscriptIngestResult:
    """Download, parse, and UPSERT transcripts for one video."""

    try:
        downloaded = fetch_video_subtitle(video_id)
        cues = parse_vtt(downloaded.content)
    except VttParseError as exc:
        message = f"Failed to parse subtitles for {video_id}: {exc}"
        LOGGER.error(message)
        raise SubtitleParseError(message) from exc
    except SubtitleIngestError as exc:
        LOGGER.error("Failed to ingest subtitles for video %s: %s", video_id, exc)
        raise

    try:
        with create_connection_pool(config) as pool:
            with pool.connection() as connection:
                for cue in cues:
                    _upsert_transcript(connection, video_id, cue)
                connection.commit()
    except TubeSiphonDatabaseError:
        LOGGER.error("Failed to ingest subtitles for video %s due to database setup", video_id)
        raise
    except (PsycopgError, RuntimeError) as exc:
        message = f"Failed to upsert transcripts for video {video_id}: {exc}"
        LOGGER.exception(message)
        raise SubtitleIngestError(message) from exc

    return VideoTranscriptIngestResult(
        video_id=downloaded.video_id,
        transcript_count=len(cues),
        subtitle_language=downloaded.language,
        subtitle_source=downloaded.source,
    )


def _fetch_video_metadata(
    video_url: str,
    *,
    yt_dlp_binary: str,
) -> Mapping[str, Any]:
    command = [
        yt_dlp_binary,
        "-J",
        "--skip-download",
        video_url,
    ]
    try:
        completed_process = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as exc:
        message = f"yt-dlp failed to start for {video_url}: {exc}"
        LOGGER.error(message)
        raise SubtitleDownloadError(message) from exc

    if completed_process.returncode != 0:
        detail = _completed_process_detail(completed_process)
        message = f"yt-dlp failed to inspect subtitles for {video_url}: {detail}"
        LOGGER.error(message)
        raise SubtitleDownloadError(message)

    try:
        payload = json.loads(completed_process.stdout)
    except json.JSONDecodeError as exc:
        message = f"yt-dlp returned invalid JSON for {video_url}: {exc}"
        LOGGER.error(message)
        raise SubtitleDownloadError(message) from exc

    if not isinstance(payload, Mapping):
        raise SubtitleDownloadError(f"yt-dlp returned unexpected JSON for {video_url}")
    return payload


def _iter_candidate_tracks(payload: Mapping[str, Any]) -> Iterator[SubtitleTrack]:
    manual = _select_from_track_mapping(payload.get("subtitles"), source="manual")
    if manual is not None:
        yield manual

    automatic = _select_from_track_mapping(
        payload.get("automatic_captions"),
        source="automatic",
    )
    if automatic is not None:
        yield automatic


def _select_from_track_mapping(
    tracks: object,
    *,
    source: SubtitleSource,
) -> SubtitleTrack | None:
    if not isinstance(tracks, Mapping) or not tracks:
        return None

    languages = [str(language) for language in tracks if str(language).strip()]
    ordered_languages = _prioritize_languages(languages)
    for language in ordered_languages:
        entries = tracks.get(language)
        if _has_vtt_entry(entries):
            return SubtitleTrack(language=language, source=source)
    return None


def _prioritize_languages(languages: Sequence[str]) -> list[str]:
    selected: list[str] = []
    for preferred in DEFAULT_LANGUAGE_PRIORITY:
        if preferred in languages:
            selected.append(preferred)
    selected.extend(language for language in languages if language not in selected)
    return selected


def _has_vtt_entry(entries: object) -> bool:
    if not isinstance(entries, list):
        return False
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        extension = str(entry.get("ext") or "").lower()
        url = str(entry.get("url") or "").lower()
        if extension == "vtt" or "fmt=vtt" in url:
            return True
    return False


def _download_track(
    video_url: str,
    track: SubtitleTrack,
    *,
    output_dir: Path,
    yt_dlp_binary: str,
) -> str:
    output_template = output_dir / "%(id)s.%(ext)s"
    write_flag = "--write-subs" if track.source == "manual" else "--write-auto-subs"
    command = [
        yt_dlp_binary,
        "--skip-download",
        write_flag,
        "--sub-langs",
        track.language,
        "--sub-format",
        "vtt",
        "-o",
        str(output_template),
        video_url,
    ]
    try:
        completed_process = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as exc:
        message = f"yt-dlp failed to start for subtitle download: {exc}"
        raise SubtitleDownloadError(message) from exc

    if completed_process.returncode != 0:
        detail = _completed_process_detail(completed_process)
        raise SubtitleDownloadError(detail)

    return _read_downloaded_vtt(output_dir, track)


def _read_downloaded_vtt(output_dir: Path, track: SubtitleTrack) -> str:
    subtitle_files = sorted(output_dir.rglob("*.vtt"))
    if not subtitle_files:
        raise SubtitleDownloadError("yt-dlp did not create a WebVTT subtitle file")

    language_marker = f".{track.language}."
    for subtitle_file in subtitle_files:
        if language_marker in subtitle_file.name:
            return subtitle_file.read_text(encoding="utf-8")
    return subtitle_files[0].read_text(encoding="utf-8")


def _upsert_transcript(connection: Any, video_id: str, cue: TranscriptCue) -> None:
    connection.execute(
        """
        INSERT INTO transcripts (video_id, start_time, text)
        VALUES (%(video_id)s, %(start_time)s, %(text)s)
        ON CONFLICT (video_id, start_time) DO UPDATE
        SET text = EXCLUDED.text
        """,
        {
            "video_id": video_id,
            "start_time": cue.start_time,
            "text": cue.text,
        },
    )


def _coerce_video_url(video_id_or_url: str) -> str:
    value = video_id_or_url.strip()
    if "://" in value:
        return value
    return f"https://www.youtube.com/watch?v={value}"


def _completed_process_detail(completed_process: object) -> str:
    stderr = str(getattr(completed_process, "stderr", "") or "").strip()
    stdout = str(getattr(completed_process, "stdout", "") or "").strip()
    return stderr or stdout or f"exit code {getattr(completed_process, 'returncode', 'unknown')}"
