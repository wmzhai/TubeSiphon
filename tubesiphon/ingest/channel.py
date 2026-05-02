"""YouTube channel metadata ingestion via yt-dlp."""

from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from tubesiphon.output.files import write_channel_files
from tubesiphon.paths import DEFAULT_OUTPUT_DIR


LOGGER = logging.getLogger(__name__)


class ChannelIngestError(Exception):
    """Base class for channel ingestion errors suitable for CLI display."""


class YtDlpError(ChannelIngestError):
    """Raised when yt-dlp cannot return usable channel metadata."""


class ChannelMetadataError(ChannelIngestError):
    """Raised when channel or video metadata cannot be parsed."""


@dataclass(frozen=True)
class VideoMetadata:
    """Metadata for one YouTube video."""

    video_id: str
    channel_id: str
    title: str | None
    upload_date: date | None
    url: str | None
    timestamp: int | None
    position: int


@dataclass(frozen=True)
class ChannelMetadata:
    """Metadata for a YouTube channel and its videos."""

    channel_id: str
    url: str
    name: str | None
    videos: list[VideoMetadata]
    skipped_video_count: int = 0


@dataclass(frozen=True)
class ChannelSyncResult:
    """Summary returned after syncing a channel to files."""

    channel_id: str
    channel_name: str | None
    video_count: int
    skipped_video_count: int
    output_dir: Path


def fetch_channel_metadata(
    channel_url: str,
    *,
    yt_dlp_binary: str = "yt-dlp",
) -> dict[str, Any]:
    """Fetch channel metadata and a flat video list using ``yt-dlp -J``."""

    listing_url = _normalize_channel_listing_url(channel_url)
    command = [
        yt_dlp_binary,
        "-J",
        "--flat-playlist",
        "--ignore-errors",
        listing_url,
    ]
    try:
        completed_process = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as exc:
        message = f"yt-dlp failed to start for {channel_url}: {exc}"
        LOGGER.error(message)
        raise YtDlpError(message) from exc

    if completed_process.returncode != 0:
        detail = (
            completed_process.stderr.strip()
            or completed_process.stdout.strip()
            or f"exit code {completed_process.returncode}"
        )
        message = f"yt-dlp failed for {channel_url}: {detail}"
        LOGGER.error(message)
        raise YtDlpError(message)

    try:
        payload = json.loads(completed_process.stdout)
    except json.JSONDecodeError as exc:
        message = f"yt-dlp returned invalid JSON for {channel_url}: {exc}"
        LOGGER.error(message)
        raise YtDlpError(message) from exc

    if not isinstance(payload, dict):
        raise YtDlpError(f"yt-dlp returned unexpected JSON for {channel_url}")
    return payload


def parse_channel_metadata(
    payload: Mapping[str, Any],
    *,
    source_url: str,
) -> ChannelMetadata:
    """Parse yt-dlp channel JSON into file-output metadata."""

    channel_id = _first_text(payload, "channel_id", "uploader_id", "id")
    if channel_id is None:
        raise ChannelMetadataError("yt-dlp metadata is missing a channel id")

    entries = payload.get("entries") or []
    if not isinstance(entries, list):
        raise ChannelMetadataError("yt-dlp metadata entries must be a list")

    videos: list[VideoMetadata] = []
    skipped_video_count = 0
    for index, entry in enumerate(entries):
        try:
            videos.append(
                _parse_video_metadata(
                    entry,
                    channel_id=channel_id,
                    position=index,
                )
            )
        except ChannelMetadataError as exc:
            skipped_video_count += 1
            LOGGER.warning(
                "Skipping video metadata at index %s for channel %s: %s",
                index,
                channel_id,
                exc,
            )

    return ChannelMetadata(
        channel_id=channel_id,
        url=_first_text(payload, "channel_url", "uploader_url", "webpage_url")
        or source_url,
        name=_first_text(payload, "channel", "uploader", "title"),
        videos=_sort_videos_newest_first(videos),
        skipped_video_count=skipped_video_count,
    )


def sync_channel(
    channel_url: str,
    *,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
) -> ChannelSyncResult:
    """Fetch a channel video list and write channel index files."""

    output_path = Path(output_dir)
    payload = fetch_channel_metadata(channel_url)
    metadata = parse_channel_metadata(payload, source_url=channel_url)
    video_entries = [_video_to_output_dict(video) for video in metadata.videos]

    channel_dir = write_channel_files(
        output_dir=output_path,
        channel_id=metadata.channel_id,
        url=metadata.url,
        name=metadata.name,
        videos=video_entries,
        failures=[],
    )

    return ChannelSyncResult(
        channel_id=metadata.channel_id,
        channel_name=metadata.name,
        video_count=len(metadata.videos),
        skipped_video_count=metadata.skipped_video_count,
        output_dir=channel_dir,
    )


def _parse_video_metadata(
    entry: object,
    *,
    channel_id: str,
    position: int,
) -> VideoMetadata:
    if not isinstance(entry, Mapping):
        raise ChannelMetadataError("video entry is not an object")

    raw_url = _first_text(entry, "url", "webpage_url")
    video_id = _first_text(entry, "id", "video_id") or _extract_video_id(raw_url)
    if video_id is None:
        raise ChannelMetadataError("missing video id")

    return VideoMetadata(
        video_id=video_id,
        channel_id=channel_id,
        title=_first_text(entry, "title"),
        upload_date=_parse_upload_date(_first_text(entry, "upload_date")),
        url=_coerce_watch_url(video_id, raw_url),
        timestamp=_first_int(entry, "timestamp", "release_timestamp"),
        position=position,
    )


def _parse_upload_date(raw_value: str | None) -> date | None:
    if raw_value is None:
        return None
    for format_string in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw_value, format_string).date()
        except ValueError:
            pass
    raise ChannelMetadataError(f"invalid upload_date {raw_value!r}")


def _video_to_output_dict(video: VideoMetadata) -> dict[str, Any]:
    return {
        "video_id": video.video_id,
        "channel_id": video.channel_id,
        "title": video.title,
        "upload_date": video.upload_date,
        "url": video.url,
        "timestamp": video.timestamp,
        "position": video.position,
    }


def _sort_videos_newest_first(videos: list[VideoMetadata]) -> list[VideoMetadata]:
    return sorted(videos, key=_video_sort_key)


def _video_sort_key(video: VideoMetadata) -> tuple[int, int, int]:
    if video.upload_date is not None:
        return (0, -video.upload_date.toordinal(), video.position)
    if video.timestamp is not None:
        return (0, -video.timestamp, video.position)
    return (1, video.position, video.position)


def _first_text(mapping: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _first_int(mapping: Mapping[str, object], *keys: str) -> int | None:
    for key in keys:
        value = mapping.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _normalize_channel_listing_url(channel_url: str) -> str:
    stripped_url = channel_url.strip()
    parsed_url = urlparse(stripped_url)
    if not parsed_url.netloc:
        return stripped_url

    host = parsed_url.netloc.lower()
    if not (host == "youtube.com" or host.endswith(".youtube.com")):
        return stripped_url

    path = parsed_url.path.rstrip("/")
    path_parts = [part for part in path.split("/") if part]
    if not path_parts:
        return stripped_url

    first_part = path_parts[0]
    is_channel_url = first_part.startswith("@") or first_part in {
        "channel",
        "c",
        "user",
    }
    if not is_channel_url or path_parts[-1] in {"videos", "shorts", "streams"}:
        return stripped_url

    return parsed_url._replace(path=f"{path}/videos").geturl()


def _extract_video_id(url: str | None) -> str | None:
    if url is None:
        return None
    if "://" not in url and "/" not in url:
        return url

    parsed_url = urlparse(url)
    query_video_id = parse_qs(parsed_url.query).get("v", [None])[0]
    if query_video_id:
        return query_video_id

    path_parts = [part for part in parsed_url.path.split("/") if part]
    if path_parts:
        return path_parts[-1]
    return None


def _coerce_watch_url(video_id: str, raw_url: str | None) -> str:
    if raw_url and raw_url.startswith("http"):
        return raw_url
    return f"https://www.youtube.com/watch?v={video_id}"
