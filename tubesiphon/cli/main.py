"""Command line entrypoint for TubeSiphon."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from tubesiphon.ingest.channel import ChannelIngestError, sync_channel
from tubesiphon.storage.db import TubeSiphonDatabaseError, initialize_database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tube-siphon",
        description="Ingest YouTube subtitles into PostgreSQL with pgvector embeddings.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    sync_parser = subparsers.add_parser(
        "sync",
        help="synchronize channel and video metadata for a YouTube channel",
    )
    sync_parser.add_argument("channel_url", help="YouTube channel URL")
    sync_parser.set_defaults(handler=_sync_channel)

    ingest_parser = subparsers.add_parser(
        "ingest",
        help="ingest subtitles for one video",
    )
    ingest_parser.add_argument("video_id", help="YouTube video ID")
    ingest_parser.set_defaults(handler=_not_implemented)

    embed_parser = subparsers.add_parser(
        "embed",
        help="generate embeddings for processed transcript chunks",
    )
    embed_parser.set_defaults(handler=_not_implemented)

    db_parser = subparsers.add_parser(
        "db",
        help="database maintenance commands",
    )
    db_subparsers = db_parser.add_subparsers(dest="db_command", metavar="db_command")
    db_init_parser = db_subparsers.add_parser(
        "init",
        help="initialize the PostgreSQL schema",
    )
    db_init_parser.set_defaults(handler=_initialize_database)
    db_parser.set_defaults(handler=_print_command_help, command_parser=db_parser)

    return parser


def _not_implemented(args: argparse.Namespace) -> int:
    print(
        f"tube-siphon {args.command} is not implemented in the project skeleton.",
        file=sys.stderr,
    )
    return 2


def _sync_channel(args: argparse.Namespace) -> int:
    try:
        result = sync_channel(args.channel_url)
    except (ChannelIngestError, TubeSiphonDatabaseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    skipped = (
        f", {result.skipped_video_count} skipped"
        if result.skipped_video_count
        else ""
    )
    print(
        f"Synchronized channel {result.channel_id}: "
        f"{result.video_count} videos metadata upserted{skipped}."
    )
    return 0


def _print_command_help(args: argparse.Namespace) -> int:
    args.command_parser.print_help()
    return 0


def _initialize_database(args: argparse.Namespace) -> int:
    del args
    try:
        initialize_database()
    except TubeSiphonDatabaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("Database schema initialized.")
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
