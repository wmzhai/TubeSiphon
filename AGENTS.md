# TubeSiphon 代理说明

TubeSiphon 是一个 Python 命令行项目，用 `yt-dlp` 抓取 YouTube 频道视频列表和字幕，并把结果写入本地文件。

实现前先读 [docs/SPEC.md](docs/SPEC.md)。

## 项目要求

- 只使用 `uv`：`uv init`、`uv add`、`uv run`。不要创建 `requirements.txt`。
- Python >= 3.11。
- 所有 YouTube 元数据和字幕都必须通过 `yt-dlp` 获取，不使用 YouTube 官方 API。
- 频道列表抓取和字幕抓取必须是两个阶段：
  - `sync <channel_url>` 只抓视频列表。
  - `ingest <channel_id>` 读取已保存的视频列表再抓字幕。
- 输出结构以 `docs/SPEC.md` 为准。
- 重复运行可以覆盖当前文件，但不能在 `videos.yaml` 里产生重复视频。
- 单个视频字幕失败要记录到 `failures.yaml`，不能中断同批次其他视频。
- 字幕抓取使用 `ThreadPoolExecutor` 并发。
- `embed` 保留入口，本轮不实现业务逻辑。

## 开发规则

- 只改当前任务需要的范围，不提前实现后续阶段。
- 完成前运行相关验证命令，并报告命令和结果。
- 如果遇到工具、网络、YouTube 访问、cookies 或 bot check 阻塞，直接说明阻塞原因，不伪造成功。
- 保持改动小而可审查。

## 测试数据规则

涉及 YouTube 获取、字幕解析、切分或依赖 YouTube 数据的测试，必须使用下面这个真实频道：

- 频道 URL：`https://www.youtube.com/@nicolasyounglive`
- 频道 ID：`UCXUP_aBLQBNFgLjvnrMTHtw`
- 已知视频 ID：`-b9Jvb3Fyqc`

测试必须联网访问 YouTube。不要在测试、文档或示例里编造频道 ID、频道名、视频 ID、观看 URL、播放列表 URL 或字幕内容。除非是在无法用真实频道覆盖的小边界上做保护，否则不要写纯 mock 测试。

注意：裸 `@handle` 频道 URL 用 `yt-dlp -J --flat-playlist` 抓取时，可能返回 Videos/Shorts 等频道标签页，而不是视频条目。抓频道列表前要规范化到 `/videos`。

运行测试：

```bash
uv run pytest
```

测试会清空项目根目录 `data/`，抓取真实频道列表，并下载前 5 个视频字幕。测试结束后保留 `data/`，方便检查真实输出。

## 固定 checkout 工作流

云端 runner 使用固定本地 checkout。

规范路径：

```text
/home/optworks/TubeSiphon
```

规范远端：

```text
git@github.com:wmzhai/TubeSiphon.git
```

处理 TubeSiphon 任务时：

- 直接在固定 checkout 中工作。
- 不要另行 clone。
- 不要使用 `multica repo checkout`。
- 不要在 Multica 任务目录和项目 checkout 之间复制文件。
- 在项目 checkout 内运行 `git status`、测试、提交和推送。
- 默认使用当前分支，除非任务明确要求新分支。
- 不要并发处理多个 TubeSiphon 任务。

## Git 规则

需要提交或推送时：

- 使用当前分支，除非用户明确要求，不新建分支或 PR。
- 提交前查看 `git status` 和 `git diff`。
- 提交前运行与当前改动相关的验证。
- 只提交当前任务相关文件，不带入无关本地改动。
- 提交信息尽量使用简洁的 Conventional Commits 风格。
- 推送到当前分支配置的 `origin`。
- 不要 force push，除非用户明确要求。
- 如果验证、提交或推送失败，停下来报告原因。
- 推送成功后报告分支、commit hash、远端 URL 和验证结果。
- 只做提交或推送请求时，不新增业务逻辑。
