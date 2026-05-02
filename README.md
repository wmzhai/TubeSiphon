# TubeSiphon

TubeSiphon 是一个 Python 命令行工具。它用 `yt-dlp` 获取 YouTube 频道视频列表和字幕，并把结果写到项目根目录的 `data/`。

详细行为约定见 [docs/SPEC.md](docs/SPEC.md)。

## 开发

安装依赖：

```bash
uv sync
```

查看命令：

```bash
uv run tube-siphon --help
```

运行测试：

```bash
uv run pytest
```

测试会先清空项目根目录 `data/`，再访问真实频道，抓取频道列表，并下载前 5 个视频字幕。测试结束后不会清理 `data/`，方便直接查看实际结果。

## 使用流程

先抓频道视频列表：

```bash
uv run tube-siphon sync "https://www.youtube.com/@nicolasyounglive"
```

再根据已保存的视频列表抓字幕：

```bash
uv run tube-siphon ingest "UCXUP_aBLQBNFgLjvnrMTHtw" --limit 5 --workers 4
```

`sync` 只写频道索引文件，不下载字幕。`ingest` 读取 `videos.yaml`，按保存顺序处理选中的视频，并把失败记录写入 `failures.yaml`。

## 输出目录

```text
data/<channel_id>/channel.yaml
data/<channel_id>/videos.yaml
data/<channel_id>/failures.yaml
data/<channel_id>/videos/<video_id>/metadata.yaml
data/<channel_id>/videos/<video_id>/transcript.yaml
data/<channel_id>/videos/<video_id>/transcript.md
data/<channel_id>/videos/<video_id>/transcript.vtt
```

## 命令

```bash
uv run tube-siphon sync <channel_url> [--output-dir data]
uv run tube-siphon ingest <channel_id> [--output-dir data] [--limit N] [--workers 4]
uv run tube-siphon embed
```

`embed` 暂未实现，只保留入口。
