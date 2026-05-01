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

Create a PostgreSQL database with the pgvector extension available, then set a
connection string. `TUBESIPHON_DATABASE_URL` is preferred when both variables
are present; `DATABASE_URL` is also supported.

```bash
export TUBESIPHON_DATABASE_URL="postgresql://user:password@localhost:5432/tubesiphon"
uv run tube-siphon db init
```

If the application database role cannot create extensions, create `vector` once
with a PostgreSQL superuser before running `db init`:

```bash
sudo -u postgres psql -d tubesiphon -c "CREATE EXTENSION IF NOT EXISTS vector;"
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
uv run tube-siphon db init
```
