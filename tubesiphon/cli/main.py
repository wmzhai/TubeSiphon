"""Command line entrypoint for TubeSiphon."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tube-siphon",
        description="Ingest YouTube subtitles into PostgreSQL with pgvector embeddings.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    sync_parser = subparsers.add_parser(
        "sync",
        help="synchronize subtitles for a YouTube channel",
    )
    sync_parser.add_argument("channel_url", help="YouTube channel URL")
    sync_parser.set_defaults(handler=_not_implemented)

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

    return parser


def _not_implemented(args: argparse.Namespace) -> int:
    print(
        f"tube-siphon {args.command} is not implemented in the project skeleton.",
        file=sys.stderr,
    )
    return 2


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
