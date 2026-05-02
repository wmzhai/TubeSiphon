"""Command line entrypoint for TubeSiphon."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from tubesiphon.ingest.channel import ChannelIngestError, sync_channel
from tubesiphon.ingest.subtitle import SubtitleIngestError, ingest_channel_subtitles
from tubesiphon.paths import DEFAULT_OUTPUT_DIR


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tube-siphon",
        description="Fetch YouTube channel subtitles into a file output directory.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    sync_parser = subparsers.add_parser(
        "sync",
        help="fetch a channel video list",
    )
    sync_parser.add_argument("channel_url", help="YouTube channel URL")
    sync_parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="directory for channel output files (default: data)",
    )
    sync_parser.set_defaults(handler=_sync_channel)

    ingest_parser = subparsers.add_parser(
        "ingest",
        help="fetch subtitles for videos saved in a channel list",
    )
    ingest_parser.add_argument("channel_id", help="YouTube channel ID")
    ingest_parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="directory for channel output files (default: data)",
    )
    ingest_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="maximum number of videos to ingest from the saved list",
    )
    ingest_parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="concurrent subtitle downloads (default: 4)",
    )
    ingest_parser.set_defaults(handler=_ingest_channel)

    embed_parser = subparsers.add_parser(
        "embed",
        help="placeholder for future file-output embedding support",
    )
    embed_parser.set_defaults(handler=_not_implemented)

    return parser


def _not_implemented(args: argparse.Namespace) -> int:
    print(
        f"tube-siphon {args.command} file-output embedding is not implemented yet.",
        file=sys.stderr,
    )
    return 2


def _sync_channel(args: argparse.Namespace) -> int:
    try:
        result = sync_channel(
            args.channel_url,
            output_dir=args.output_dir,
        )
    except ChannelIngestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    skipped = (
        f", {result.skipped_video_count} skipped"
        if result.skipped_video_count
        else ""
    )
    print(
        f"Synchronized channel {result.channel_id}: "
        f"{result.video_count} videos listed{skipped}. "
        f"Output: {result.output_dir}"
    )
    return 0


def _ingest_channel(args: argparse.Namespace) -> int:
    try:
        result = ingest_channel_subtitles(
            args.channel_id,
            output_dir=args.output_dir,
            limit=args.limit,
            workers=args.workers,
        )
    except SubtitleIngestError as exc:
        LOGGER.error(
            "Failed to ingest subtitles for channel %s: %s",
            args.channel_id,
            exc,
        )
        print(f"error: {exc}", file=sys.stderr)
        return 1

    failed = f", {result.failure_count} failed" if result.failure_count else ""
    print(
        f"Ingested subtitles for channel {result.channel_id}: "
        f"{result.ingested_video_count}/{result.requested_video_count} videos "
        f"written{failed}. "
        f"Output: {result.output_dir}"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
