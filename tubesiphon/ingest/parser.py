"""WebVTT transcript parsing helpers."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass


TIMING_RE = re.compile(
    r"(?P<start>(?:\d{2}:)?\d{2}:\d{2}\.\d{3})\s+-->\s+"
    r"(?P<end>(?:\d{2}:)?\d{2}:\d{2}\.\d{3})"
)
INLINE_TIMESTAMP_RE = re.compile(r"<(?:\d{2}:)?\d{2}:\d{2}\.\d{3}>")
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


class VttParseError(Exception):
    """Raised when a WebVTT file cannot produce transcript cues."""


@dataclass(frozen=True)
class TranscriptCue:
    """One transcript row ready for storage."""

    start_time: float
    text: str


def parse_vtt(vtt_text: str) -> list[TranscriptCue]:
    """Parse WebVTT text into cleaned transcript cues."""

    cues: list[TranscriptCue] = []
    seen: set[tuple[float, str]] = set()
    normalized_text = vtt_text.replace("\r\n", "\n").replace("\r", "\n")

    for block in re.split(r"\n\s*\n", normalized_text):
        lines = [line.strip().lstrip("\ufeff") for line in block.splitlines()]
        lines = [line for line in lines if line]
        if not lines or _is_non_cue_block(lines[0]):
            continue

        timing_index, timing_match = _find_timing_line(lines)
        if timing_match is None:
            continue

        start_time = _parse_timestamp(timing_match.group("start"))
        text = _clean_cue_text(lines[timing_index + 1 :])
        if not text:
            continue

        key = (start_time, text)
        if key in seen:
            continue
        seen.add(key)
        cues.append(TranscriptCue(start_time=start_time, text=text))

    if not cues:
        raise VttParseError("No transcript cues found in VTT")
    return cues


def _is_non_cue_block(first_line: str) -> bool:
    upper_line = first_line.upper()
    return upper_line.startswith(("WEBVTT", "NOTE", "STYLE", "REGION"))


def _find_timing_line(lines: list[str]) -> tuple[int, re.Match[str] | None]:
    for index, line in enumerate(lines):
        match = TIMING_RE.search(line)
        if match is not None:
            return index, match
    return -1, None


def _parse_timestamp(timestamp: str) -> float:
    parts = timestamp.split(":")
    seconds = float(parts[-1])
    minutes = int(parts[-2])
    hours = int(parts[-3]) if len(parts) == 3 else 0
    return round((hours * 3600) + (minutes * 60) + seconds, 3)


def _clean_cue_text(lines: list[str]) -> str:
    cleaned_lines: list[str] = []
    seen_lines: set[str] = set()
    for line in lines:
        if "-->" in line:
            continue
        cleaned = INLINE_TIMESTAMP_RE.sub("", line)
        cleaned = TAG_RE.sub("", cleaned)
        cleaned = WHITESPACE_RE.sub(" ", html.unescape(cleaned)).strip()
        if not cleaned or cleaned in seen_lines:
            continue
        seen_lines.add(cleaned)
        cleaned_lines.append(cleaned)
    return WHITESPACE_RE.sub(" ", " ".join(cleaned_lines)).strip()
