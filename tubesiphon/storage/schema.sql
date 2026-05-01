CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS channels (
    channel_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT channels_url_key UNIQUE (url)
);

CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    title TEXT,
    upload_date DATE,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transcripts (
    id BIGSERIAL PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    start_time DOUBLE PRECISION NOT NULL,
    text TEXT NOT NULL,
    CONSTRAINT transcripts_video_id_start_time_key UNIQUE (video_id, start_time)
);

CREATE TABLE IF NOT EXISTS chunks (
    id BIGSERIAL PRIMARY KEY,
    video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    CONSTRAINT chunks_video_id_chunk_index_key UNIQUE (video_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS embeddings (
    id BIGSERIAL PRIMARY KEY,
    chunk_id BIGINT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    embedding vector(1536) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT embeddings_chunk_id_key UNIQUE (chunk_id)
);

CREATE INDEX IF NOT EXISTS videos_channel_id_idx
    ON videos (channel_id);

CREATE INDEX IF NOT EXISTS transcripts_video_id_idx
    ON transcripts (video_id);

CREATE INDEX IF NOT EXISTS chunks_video_id_idx
    ON chunks (video_id);

CREATE INDEX IF NOT EXISTS embeddings_chunk_id_idx
    ON embeddings (chunk_id);

CREATE INDEX IF NOT EXISTS embeddings_embedding_ivfflat_cosine_idx
    ON embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
