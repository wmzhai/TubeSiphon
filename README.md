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

## Database Initialization

Initialize a PostgreSQL database with the pgvector extension available:

```bash
psql "$DATABASE_URL" -f tubesiphon/storage/schema.sql
```

The schema uses `CREATE EXTENSION IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`,
and `CREATE INDEX IF NOT EXISTS`, so rerunning it is safe for the current schema.
Changing an existing incompatible schema should be handled with a migration.

Available skeleton CLI commands:

These commands are currently skeleton entrypoints; business logic is not implemented yet.

```bash
uv run tube-siphon sync <channel_url>
uv run tube-siphon ingest <video_id>
uv run tube-siphon embed
```
