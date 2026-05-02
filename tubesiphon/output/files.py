"""Write TubeSiphon channel and transcript outputs to files."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import yaml


class FileOutputError(Exception):
    """Raised when output files cannot be written."""


def write_channel_files(
    *,
    output_dir: Path | str,
    channel_id: str,
    url: str | None,
    name: str | None,
    videos: Sequence[Mapping[str, Any]],
    failures: Sequence[Mapping[str, Any]],
) -> Path:
    """Write channel-level YAML files and return the channel directory."""

    channel_dir = Path(output_dir) / channel_id
    channel_dir.mkdir(parents=True, exist_ok=True)

    _write_yaml(
        channel_dir / "channel.yaml",
        {
            "channel_id": channel_id,
            "url": url,
            "name": name,
        },
    )
    _write_yaml(
        channel_dir / "videos.yaml",
        {
            "channel_id": channel_id,
            "videos": _dedupe_video_entries(videos),
        },
    )
    _write_yaml(
        channel_dir / "failures.yaml",
        {
            "channel_id": channel_id,
            "failures": [_normalize_value(failure) for failure in failures],
        },
    )
    return channel_dir


def write_channel_failures(
    *,
    output_dir: Path | str,
    channel_id: str,
    failures: Sequence[Mapping[str, Any]],
) -> Path:
    """Write the channel failure index and return the channel directory."""

    channel_dir = Path(output_dir) / channel_id
    channel_dir.mkdir(parents=True, exist_ok=True)
    _write_yaml(
        channel_dir / "failures.yaml",
        {
            "channel_id": channel_id,
            "failures": [_normalize_value(failure) for failure in failures],
        },
    )
    return channel_dir


def read_yaml_mapping(path: Path) -> dict[str, Any]:
    """Read a YAML mapping, returning an empty mapping for missing files."""

    return _read_yaml_mapping(path)


def upsert_channel_video(
    *,
    output_dir: Path | str,
    channel_id: str,
    url: str | None,
    name: str | None,
    video: Mapping[str, Any],
) -> Path:
    """Create or update one video in the channel index."""

    channel_dir = Path(output_dir) / channel_id
    existing_channel = _read_yaml_mapping(channel_dir / "channel.yaml")
    existing_videos = _read_yaml_mapping(channel_dir / "videos.yaml").get("videos", [])
    existing_failures = _read_yaml_mapping(channel_dir / "failures.yaml").get(
        "failures",
        [],
    )

    videos: list[Mapping[str, Any]] = []
    if isinstance(existing_videos, list):
        videos.extend(item for item in existing_videos if isinstance(item, Mapping))

    video_id = str(video.get("video_id") or "").strip()
    if not video_id:
        raise FileOutputError("video metadata is missing video_id")

    filtered_videos = [
        existing
        for existing in videos
        if str(existing.get("video_id") or "").strip() != video_id
    ]
    filtered_videos.append(video)

    failures = (
        [item for item in existing_failures if isinstance(item, Mapping)]
        if isinstance(existing_failures, list)
        else []
    )
    return write_channel_files(
        output_dir=output_dir,
        channel_id=channel_id,
        url=url or _optional_text(existing_channel.get("url")),
        name=name or _optional_text(existing_channel.get("name")),
        videos=filtered_videos,
        failures=failures,
    )


def write_video_files(
    *,
    output_dir: Path | str,
    channel_id: str,
    metadata: Mapping[str, Any],
    language: str,
    source: str,
    cues: Sequence[Any],
    vtt_content: str,
) -> Path:
    """Write one video's metadata, transcript YAML, Markdown, and VTT files."""

    video_id = str(metadata.get("video_id") or "").strip()
    if not video_id:
        raise FileOutputError("video metadata is missing video_id")

    video_dir = Path(output_dir) / channel_id / "videos" / video_id
    video_dir.mkdir(parents=True, exist_ok=True)

    normalized_cues = [_cue_to_mapping(cue) for cue in cues]
    normalized_metadata = _normalize_value(dict(metadata))
    transcript = {
        "video_id": video_id,
        "language": language,
        "source": source,
        "cues": normalized_cues,
    }

    _write_yaml(video_dir / "metadata.yaml", normalized_metadata)
    _write_yaml(video_dir / "transcript.yaml", transcript)
    _write_text(
        video_dir / "transcript.md",
        _render_markdown_transcript(
            title=str(metadata.get("title") or video_id),
            cues=normalized_cues,
        ),
    )
    _write_text(video_dir / "transcript.vtt", vtt_content)
    return video_dir


def _dedupe_video_entries(videos: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for video in videos:
        video_id = str(video.get("video_id") or "").strip()
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        deduped.append(_normalize_value(dict(video)))
    return deduped


def _cue_to_mapping(cue: Any) -> dict[str, Any]:
    if isinstance(cue, Mapping):
        start_time = cue.get("start_time")
        text = cue.get("text")
    else:
        start_time = getattr(cue, "start_time", None)
        text = getattr(cue, "text", None)

    return {
        "start_time": round(float(start_time), 3),
        "text": str(text or ""),
    }


def _render_markdown_transcript(
    *,
    title: str,
    cues: Sequence[Mapping[str, Any]],
) -> str:
    lines = [f"# {title}", ""]
    for cue in cues:
        lines.append(f"[{_format_timestamp(float(cue['start_time']))}] {cue['text']}")
    return "\n".join(lines) + "\n"


def _format_timestamp(start_time: float) -> str:
    total_milliseconds = int(round(start_time * 1000))
    milliseconds = total_milliseconds % 1000
    total_seconds = total_milliseconds // 1000
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def _write_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    _write_text(
        path,
        yaml.safe_dump(
            _normalize_value(dict(payload)),
            sort_keys=False,
            allow_unicode=True,
        ),
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
        ) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)
        os.replace(temp_path, path)
    except OSError as exc:
        raise FileOutputError(f"Failed to write {path}: {exc}") from exc
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_value(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_value(item) for item in value]
    return value
