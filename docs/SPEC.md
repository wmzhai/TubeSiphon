# TubeSiphon 规格

TubeSiphon 用 `yt-dlp` 获取 YouTube 频道视频列表和字幕，并把结果写成目录文件。频道列表抓取和字幕抓取是两个独立阶段。

## 环境与依赖

- 使用 `uv` 管理项目和运行命令，不创建 `requirements.txt`。
- Python >= 3.11。
- 运行依赖：`yt-dlp`、`PyYAML`。
- 测试依赖：`pytest`。
- 所有 YouTube 数据只能通过 `yt-dlp` 获取，不使用 YouTube 官方 API。

## 命令

```bash
uv run tube-siphon sync <channel_url> [--output-dir data]
uv run tube-siphon ingest <channel_id> [--output-dir data] [--limit N] [--workers 4]
uv run tube-siphon embed
```

- `sync`：把频道 URL 规范化到 `/videos`，只抓视频列表并写入频道索引。
- `ingest`：读取已保存的 `videos.yaml`，按保存顺序抓取字幕。
- `--limit`：限制本次处理的视频数量，测试默认抓前 5 个。
- `--workers`：控制字幕下载并发数。
- `embed`：暂未实现。

默认输出目录是项目根目录的 `data/`。

## 数据规则

- `videos.yaml` 按新到旧保存视频。若 `yt-dlp` 的扁平列表没有日期，则保持返回顺序。
- 字幕下载优先使用人工字幕，失败或不存在时再尝试自动字幕。
- 单个视频失败只记录到 `failures.yaml`，不影响本批次其他视频。
- 重复运行会覆盖当前输出，视频索引按 `video_id` 去重。
- YAML 使用 `yaml.safe_dump(sort_keys=False, allow_unicode=True)`。

## 输出结构

```text
data/<channel_id>/channel.yaml
data/<channel_id>/videos.yaml
data/<channel_id>/failures.yaml
data/<channel_id>/videos/<video_id>/metadata.yaml
data/<channel_id>/videos/<video_id>/transcript.yaml
data/<channel_id>/videos/<video_id>/transcript.md
data/<channel_id>/videos/<video_id>/transcript.vtt
```

文件内容：

- `channel.yaml`：`channel_id`、频道 URL、频道名。
- `videos.yaml`：`channel_id` 和视频列表。
- `failures.yaml`：最近一次字幕抓取的失败视频。
- `metadata.yaml`：视频 ID、频道 ID、标题、观看 URL。
- `transcript.yaml`：视频 ID、语言、字幕来源、`cues[{start_time, text}]`。
- `transcript.md`：标题作为 H1，每条字幕为 `[HH:MM:SS.mmm] text`。
- `transcript.vtt`：保留原始 WebVTT 内容。

## 测试

```bash
uv run pytest
```

测试直接访问真实频道 `https://www.youtube.com/@nicolasyounglive`。开始前会清空项目根目录 `data/`，随后抓频道列表并下载前 5 个视频字幕。测试结束后保留 `data/`，供人工检查实际抓取结果。
