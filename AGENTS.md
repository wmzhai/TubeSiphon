# TubeSiphon Agent Instructions

Project: TubeSiphon, a Python CLI pipeline for ingesting YouTube channel subtitles into PostgreSQL + pgvector.

Hard requirements:
- Use `uv` only: `uv init`, `uv add`, `uv run`. Do not create requirements.txt.
- Python >= 3.11.
- All YouTube metadata/subtitle retrieval must use `yt-dlp`; do not use YouTube official APIs.
- PostgreSQL storage must use `psycopg`, `psycopg-pool`, and `pgvector`.
- Pipeline operations must be idempotent via UPSERT/unique constraints.
- Single video failures must be logged and must not abort the whole channel sync.
- Use ThreadPoolExecutor for concurrent subtitle retrieval.
- Provide CLI commands: `sync <channel_url>`, `ingest <video_id>`, `embed`.

Read `docs/SPEC.md` before implementing.
