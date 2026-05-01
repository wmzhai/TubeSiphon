"""YouTube channel metadata ingestion via yt-dlp."""

from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

from psycopg import Error as PsycopgError

from tubesiphon.storage.db import DatabaseConfig, create_connection_pool


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
    """Summary returned after syncing channel/video metadata."""

    channel_id: str
    channel_name: str | None
    video_count: int
    skipped_video_count: int


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
    """Parse yt-dlp channel JSON into storage-ready metadata."""

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
            videos.append(_parse_video_metadata(entry, channel_id=channel_id))
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
        videos=videos,
        skipped_video_count=skipped_video_count,
    )


def sync_channel(
    channel_url: str,
    *,
    config: DatabaseConfig | str | None = None,
) -> ChannelSyncResult:
    """Fetch channel/video metadata and UPSERT it into PostgreSQL."""

    payload = fetch_channel_metadata(channel_url)
    metadata = parse_channel_metadata(payload, source_url=channel_url)
    written_video_count = 0
    skipped_video_count = metadata.skipped_video_count

    with create_connection_pool(config) as pool:
        with pool.connection() as connection:
            _upsert_channel(connection, metadata)
            for video in metadata.videos:
                try:
                    _upsert_video(connection, video)
                except (PsycopgError, RuntimeError) as exc:
                    skipped_video_count += 1
                    LOGGER.exception(
                        "Skipping video %s for channel %s after database upsert "
                        "failure: %s",
                        video.video_id,
                        metadata.channel_id,
                        exc,
                    )
                    continue
                written_video_count += 1
            connection.commit()

    return ChannelSyncResult(
        channel_id=metadata.channel_id,
        channel_name=metadata.name,
        video_count=written_video_count,
        skipped_video_count=skipped_video_count,
    )


def _parse_video_metadata(
    entry: object,
    *,
    channel_id: str,
) -> VideoMetadata:
    if not isinstance(entry, Mapping):
        raise ChannelMetadataError("video entry is not an object")

    video_id = _first_text(entry, "id", "video_id") or _extract_video_id(
        _first_text(entry, "url", "webpage_url")
    )
    if video_id is None:
        raise ChannelMetadataError("missing video id")

    return VideoMetadata(
        video_id=video_id,
        channel_id=channel_id,
        title=_first_text(entry, "title"),
        upload_date=_parse_upload_date(_first_text(entry, "upload_date")),
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


def _upsert_channel(connection: Any, metadata: ChannelMetadata) -> None:
    connection.execute(
        """
        INSERT INTO channels (channel_id, url, name)
        VALUES (%(channel_id)s, %(url)s, %(name)s)
        ON CONFLICT (channel_id) DO UPDATE
        SET url = EXCLUDED.url,
            name = COALESCE(EXCLUDED.name, channels.name)
        """,
        {
            "channel_id": metadata.channel_id,
            "url": metadata.url,
            "name": metadata.name,
        },
    )


def _upsert_video(connection: Any, metadata: VideoMetadata) -> None:
    connection.execute(
        """
        INSERT INTO videos (video_id, channel_id, title, upload_date, fetched_at)
        VALUES (
            %(video_id)s,
            %(channel_id)s,
            %(title)s,
            %(upload_date)s,
            NOW()
        )
        ON CONFLICT (video_id) DO UPDATE
        SET channel_id = EXCLUDED.channel_id,
            title = COALESCE(EXCLUDED.title, videos.title),
            upload_date = COALESCE(EXCLUDED.upload_date, videos.upload_date),
            fetched_at = NOW()
        """,
        {
            "video_id": metadata.video_id,
            "channel_id": metadata.channel_id,
            "title": metadata.title,
            "upload_date": metadata.upload_date,
        },
    )


def _first_text(mapping: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
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
    is_channel_url = (
        first_part.startswith("@")
        or first_part in {"channel", "c", "user"}
    )
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
