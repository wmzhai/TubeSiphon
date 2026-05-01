# TubeSiphon Spec

构建一个 Python 项目 **TubeSiphon**：输入 YouTube 频道 URL，批量抓取所有视频字幕，完成清洗、分块、embedding，并存入 PostgreSQL。

## 环境与依赖管理
- 必须使用 uv 管理项目
- 使用 `uv init` 初始化项目
- 使用 `uv add` 添加依赖
- 使用 `uv run` 执行 CLI
- 生成 `pyproject.toml`（不要使用 requirements.txt）
- Python >= 3.11

## 核心依赖
- yt-dlp
- psycopg[binary]
- psycopg-pool
- pgvector
- sentence-transformers（或其他 embedding 模型）
- tqdm（可选）

## 要求
- 所有 YouTube 数据必须使用 `yt-dlp` 获取（禁止使用官方 API）
- 使用 PostgreSQL 存储
- 使用 connection pool
- 使用 pgvector 存储 embedding
- 提供 CLI 工具
- 支持并发执行
- 所有步骤必须幂等（可重复执行不产生重复数据）
- 支持增量同步（避免重复抓取/处理）
- 单个视频失败不能影响整体流程

## Pipeline
1. 使用 `yt-dlp -J` 获取频道视频列表
2. videos 表 UPSERT
3. 下载字幕（优先人工字幕 → 自动字幕 fallback）
4. 解析 `.vtt` → (start_time, text)
5. 文本清洗（去重、去噪）
6. 文本分块（200~400 tokens）
7. 生成 embedding
8. 写入数据库

## 项目结构
```text
tubesiphon/
  ingest/ (channel.py, subtitle.py, parser.py)
  process/ (clean.py, chunk.py, embed.py)
  storage/ (db.py, schema.sql)
  cli/ (main.py)
  config/
  data/
```

## PostgreSQL Schema
```sql
channels(
  channel_id TEXT PRIMARY KEY,
  url TEXT UNIQUE,
  name TEXT,
  created_at TIMESTAMP DEFAULT NOW()
)

videos(
  video_id TEXT PRIMARY KEY,
  channel_id TEXT,
  title TEXT,
  upload_date DATE,
  fetched_at TIMESTAMP DEFAULT NOW()
)

transcripts(
  id BIGSERIAL PRIMARY KEY,
  video_id TEXT,
  start_time DOUBLE PRECISION,
  text TEXT,
  UNIQUE(video_id, start_time)
)

chunks(
  id BIGSERIAL PRIMARY KEY,
  video_id TEXT,
  chunk_index INTEGER,
  text TEXT,
  UNIQUE(video_id, chunk_index)
)

embeddings(
  id BIGSERIAL PRIMARY KEY,
  chunk_id BIGINT,
  embedding vector(1536)
)
```

## 索引
- transcripts(video_id)
- chunks(video_id)
- embeddings 使用 ivfflat + cosine

## CLI
```bash
uv run tube-siphon sync <channel_url>
uv run tube-siphon ingest <video_id>
uv run tube-siphon embed
```

## 并发
使用 ThreadPoolExecutor 控制并发抓取字幕

## 错误处理
- try/except + logging
- 失败记录但不中断流程

## 输出
- 完整项目代码
- pyproject.toml
- schema.sql
- README.md
