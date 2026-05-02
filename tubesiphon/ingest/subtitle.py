"""Single-video subtitle download and transcript file output."""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from tubesiphon.ingest.parser import VttParseError, parse_vtt
from tubesiphon.output.files import (
    FileOutputError,
    read_yaml_mapping,
    upsert_channel_video,
    write_channel_failures,
    write_video_files,
)
from tubesiphon.paths import DEFAULT_OUTPUT_DIR


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


class SubtitleMetadataError(SubtitleIngestError):
    """Raised when yt-dlp metadata is missing required channel ownership."""


class SubtitleOutputError(SubtitleIngestError):
    """Raised when transcript output files cannot be written."""


@dataclass(frozen=True)
class SubtitleTrack:
    """A chosen subtitle track from yt-dlp metadata."""

    language: str
    source: SubtitleSource


@dataclass(frozen=True)
class DownloadedSubtitle:
    """Downloaded WebVTT content and its source metadata."""

    video_id: str
    channel_id: str | None
    channel_name: str | None
    channel_url: str | None
    title: str | None
    webpage_url: str | None
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
    output_dir: Path


@dataclass(frozen=True)
class ChannelSubtitleIngestResult:
    """Summary returned after ingesting transcripts from a channel video list."""

    channel_id: str
    requested_video_count: int
    ingested_video_count: int
    failure_count: int
    output_dir: Path


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
    resolved_video_id = _first_text(payload, "id") or video_id.strip()
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
                channel_id=_first_text(payload, "channel_id", "uploader_id"),
                channel_name=_first_text(payload, "channel", "uploader"),
                channel_url=_first_text(payload, "channel_url", "uploader_url"),
                title=_first_text(payload, "title", "fulltitle"),
                webpage_url=_first_text(payload, "webpage_url", "original_url")
                or video_url,
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
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    update_channel_index: bool = True,
    expected_channel_id: str | None = None,
) -> VideoTranscriptIngestResult:
    """Download, parse, and write transcript files for one video."""

    try:
        downloaded = fetch_video_subtitle(video_id)
    except SubtitleIngestError as exc:
        LOGGER.error("Failed to ingest subtitles for video %s: %s", video_id, exc)
        raise

    if not downloaded.channel_id:
        message = f"yt-dlp metadata for {downloaded.video_id} is missing channel_id"
        LOGGER.error(message)
        raise SubtitleMetadataError(message)
    if expected_channel_id is not None and downloaded.channel_id != expected_channel_id:
        message = (
            f"yt-dlp metadata for {downloaded.video_id} has channel_id "
            f"{downloaded.channel_id}, expected {expected_channel_id}"
        )
        LOGGER.error(message)
        raise SubtitleMetadataError(message)

    try:
        cues = parse_vtt(downloaded.content)
    except VttParseError as exc:
        message = f"Failed to parse subtitles for {video_id}: {exc}"
        LOGGER.error(message)
        raise SubtitleParseError(message) from exc

    video_metadata = {
        "video_id": downloaded.video_id,
        "channel_id": downloaded.channel_id,
        "title": downloaded.title,
        "url": downloaded.webpage_url or _coerce_video_url(downloaded.video_id),
    }
    channel_url = downloaded.channel_url or (
        f"https://www.youtube.com/channel/{downloaded.channel_id}"
    )

    try:
        if update_channel_index:
            upsert_channel_video(
                output_dir=output_dir,
                channel_id=downloaded.channel_id,
                url=channel_url,
                name=downloaded.channel_name,
                video=video_metadata,
            )
        video_dir = write_video_files(
            output_dir=output_dir,
            channel_id=downloaded.channel_id,
            metadata=video_metadata,
            language=downloaded.language,
            source=downloaded.source,
            cues=cues,
            vtt_content=downloaded.content,
        )
    except FileOutputError as exc:
        message = f"Failed to write transcript files for {downloaded.video_id}: {exc}"
        LOGGER.error(message)
        raise SubtitleOutputError(message) from exc

    return VideoTranscriptIngestResult(
        video_id=downloaded.video_id,
        transcript_count=len(cues),
        subtitle_language=downloaded.language,
        subtitle_source=downloaded.source,
        output_dir=video_dir,
    )


def ingest_channel_subtitles(
    channel_id: str,
    *,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    limit: int | None = None,
    workers: int = 4,
) -> ChannelSubtitleIngestResult:
    """Read a channel video list and fetch subtitles in saved order."""

    if workers < 1:
        raise SubtitleIngestError("--workers must be at least 1")
    if limit is not None and limit < 1:
        raise SubtitleIngestError("--limit must be at least 1")

    output_path = Path(output_dir)
    channel_dir = output_path / channel_id
    videos_yaml_path = channel_dir / "videos.yaml"
    videos_yaml = read_yaml_mapping(videos_yaml_path)
    videos = videos_yaml.get("videos")
    if not isinstance(videos, list):
        raise SubtitleIngestError(f"Video list not found: {videos_yaml_path}")

    selected_videos = [
        video for video in videos if isinstance(video, Mapping) and video.get("video_id")
    ]
    if limit is not None:
        selected_videos = selected_videos[:limit]

    failures: list[dict[str, str]] = []
    ingested_video_count = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_video = {
            executor.submit(
                ingest_video,
                str(video["video_id"]),
                output_dir=output_path,
                update_channel_index=False,
                expected_channel_id=channel_id,
            ): video
            for video in selected_videos
        }
        for future in as_completed(future_to_video):
            video = future_to_video[future]
            video_id = str(video["video_id"])
            try:
                future.result()
            except Exception as exc:
                failures.append(
                    {
                        "video_id": video_id,
                        "error": str(exc) or exc.__class__.__name__,
                    }
                )
                LOGGER.warning(
                    "Skipping video %s for channel %s after subtitle failure: %s",
                    video_id,
                    channel_id,
                    exc,
                )
                continue
            ingested_video_count += 1

    failures.sort(key=lambda failure: _video_position(failure["video_id"], selected_videos))
    write_channel_failures(
        output_dir=output_path,
        channel_id=channel_id,
        failures=failures,
    )
    return ChannelSubtitleIngestResult(
        channel_id=channel_id,
        requested_video_count=len(selected_videos),
        ingested_video_count=ingested_video_count,
        failure_count=len(failures),
        output_dir=channel_dir,
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


def _coerce_video_url(video_id_or_url: str) -> str:
    value = video_id_or_url.strip()
    if "://" in value:
        return value
    return f"https://www.youtube.com/watch?v={value}"


def _first_text(mapping: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _video_position(video_id: str, videos: Sequence[Mapping[str, object]]) -> int:
    for index, video in enumerate(videos):
        if str(video.get("video_id") or "") == video_id:
            return index
    return len(videos)


def _completed_process_detail(completed_process: object) -> str:
    stderr = str(getattr(completed_process, "stderr", "") or "").strip()
    stdout = str(getattr(completed_process, "stdout", "") or "").strip()
    return stderr or stdout or f"exit code {getattr(completed_process, 'returncode', 'unknown')}"
