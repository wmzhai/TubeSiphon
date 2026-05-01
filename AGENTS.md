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

## YouTube test data policy

For work that touches YouTube fetching, subtitles, transcript parsing, chunking,
or later pipeline stages that depend on YouTube data, use real channel data from
this canonical channel instead of invented channel/video metadata:

- Channel URL: `https://www.youtube.com/@nicolasyounglive`
- Expected channel id: `UCXUP_aBLQBNFgLjvnrMTHtw`
- Known video id that should appear in the channel video list: `-b9Jvb3Fyqc`

Default tests must use recorded fixtures captured from this real channel. Do
not invent YouTube channel IDs, channel names, video IDs, watch URLs, playlist
URLs, or subtitles in tests, docs, or examples. Live tests should hit YouTube
directly when network and YouTube access are available. Mocking is still
acceptable at process, database, or error boundaries when the data flowing
through those boundaries is from the real channel fixture.

Important lesson from OPT-14: a bare YouTube `@handle` URL may return channel
tabs such as Videos/Shorts instead of actual videos when fetched with
`yt-dlp -J --flat-playlist`. Channel-list fetching should normalize bare
channel URLs to their `/videos` listing before parsing video entries.

Run the live fixture explicitly with:

```bash
TUBESIPHON_RUN_LIVE_TESTS=1 uv run python -m unittest tests.test_live_channel_fixture
```

If the live check is blocked by cookies, bot checks, network, or PostgreSQL
credentials, report that blocker plainly in the issue comment. Do not replace
the live check with invented data.

The repository includes a guard test that fails if common invented YouTube
placeholder metadata is reintroduced:

```bash
uv run python -m unittest tests.test_youtube_test_data_policy
```

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
