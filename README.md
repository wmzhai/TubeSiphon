# TubeSiphon

TubeSiphon ingests YouTube channel subtitles into PostgreSQL with pgvector embeddings.

Implementation spec: `docs/SPEC.md`.

## Local Development

Install and sync the project environment:

```bash
uv sync
```

Show CLI help:

```bash
uv run tube-siphon --help
```

Available skeleton CLI commands:

These commands are currently skeleton entrypoints; business logic is not implemented yet.

```bash
uv run tube-siphon sync <channel_url>
uv run tube-siphon ingest <video_id>
uv run tube-siphon embed
```
