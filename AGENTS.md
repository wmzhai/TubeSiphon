# TubeSiphon Agent Instructions

Project: TubeSiphon, a Python CLI pipeline for ingesting YouTube channel subtitles into PostgreSQL + pgvector.

Read `docs/SPEC.md` before implementing.

## Project requirements

- Use `uv` only: `uv init`, `uv add`, `uv run`. Do not create requirements.txt.
- Python >= 3.11.
- All YouTube metadata/subtitle retrieval must use `yt-dlp`; do not use YouTube official APIs.
- PostgreSQL storage must use `psycopg`, `psycopg-pool`, and `pgvector`.
- Pipeline operations must be idempotent via UPSERT/unique constraints.
- Single video failures must be logged and must not abort the whole channel sync.
- Use ThreadPoolExecutor for concurrent subtitle retrieval.
- Provide CLI commands: `sync <channel_url>`, `ingest <video_id>`, `embed`.

## Development workflow

- Keep changes scoped to the current issue. Do not implement future pipeline stages unless the issue explicitly asks for them.
- Before reporting completion, run verification commands relevant to the changed area and report the exact commands/results.
- If a requirement is blocked by local tools, credentials, network access, PostgreSQL, or YouTube access, stop and report the blocker instead of faking success.
- Prefer small, reviewable changes over broad rewrites.

## Fixed local checkout workflow

This project uses a fixed local checkout on the cloud runner.

Canonical local path:
`/home/optworks/TubeSiphon`

Canonical remote:
`git@github.com:wmzhai/TubeSiphon.git`

When working on TubeSiphon issues:
- Work directly in `/home/optworks/TubeSiphon`.
- Do not create a separate clone for this project.
- Do not use `multica repo checkout` for this project.
- Do not copy files between the Multica task workdir and the project checkout.
- Run git status, tests, commit, and push from `/home/optworks/TubeSiphon`.
- This is a solo workflow; use the current branch unless the issue says otherwise.
- Do not run multiple TubeSiphon tasks concurrently against this shared checkout.

## Git workflow

This is a solo project workflow unless an issue says otherwise.

When asked to commit or push:
- Use the current branch. Do not create a new branch or PR unless explicitly requested.
- Review `git status` and `git diff` before committing.
- Run verification relevant to the current issue before committing.
- Commit only files related to the current issue; do not include unrelated local changes.
- Use a concise Conventional Commits style message when practical.
- Push to the configured `origin` for the current branch.
- Never force push unless explicitly requested.
- If verification, commit, or push fails, stop and report the reason.
- After a successful push, report the branch, commit hash, remote URL, and verification results.
- Do not implement new business logic during a commit/push-only request.
