# pylingual-web-batch

通过 pylingual Web API 批量反编译 Python 字节码，并支持队列控制、断点续跑和失败恢复。

[English](README.md) | **简体中文**

## 项目特点

- 递归发现 `.pyc` 文件
- 批量上传到 pylingual Web API
- 支持并发数和远端队列位置控制
- 本地超时后保留服务端任务 `identifier`
- 下次运行继续轮询，不重复上传
- 区分网络错误、超时和服务端永久反编译失败
- 原子写入状态文件和反编译结果
- 支持命令行和 Python API
- 不包含任何业务项目代码或服务端凭据

## 安装

当前尚未发布到 PyPI，可以直接从 GitHub 安装：

```bash
python -m pip install "git+https://github.com/ttungx/pylingual-web-batch.git"
```

本地开发安装：

```bash
python -m pip install -e ".[dev]"
```

发布到 PyPI 后可以使用：

```bash
python -m pip install pylingual-web-batch
```

仓库已配置 PyPI Trusted Publishing 工作流。管理员在 PyPI 项目设置中将
`Ttungx/pylingual-web-batch` 的 `pypi` environment 配置为可信发布者后，
创建并发布 GitHub Release 即可自动发布到 PyPI。工作流不保存 PyPI Token。
如果 GitHub 使用 `GITHUB_TOKEN` 创建 Release，GitHub 不会递归触发 release 事件；本项目已用
`workflow_run` 监听成功的 `release` workflow，并保留 `workflow_dispatch` 作为手动补发入口。

发布前先在本地检查：

```bash
python -m pip install --upgrade build twine
rm -rf dist build *.egg-info
python -m build
python -m twine check dist/*
```

然后创建新版本标签并发布 GitHub Release：

```bash
git tag v0.1.1
git push origin v0.1.1
```

版本号不能重复；正式发布后不要重新上传同一个版本号。

## 快速开始

将有权处理的 `.pyc` 文件放入输入目录：

```bash
pylingual-web-batch run ./input -o ./output
```

程序会递归扫描输入目录。默认只处理 `*.pyc`，并自动排除 `__pycache__` 目录。
已有输出文件默认跳过，只有显式指定 `--reupload` 才会重新处理。

## 常用命令

### 批量运行

```bash
pylingual-web-batch run ./input -o ./output \
  --state ./.pylingual-state.json \
  --lock-file ./.pylingual-batch.lock \
  --jobs 1 \
  --queue-limit 10 \
  --poll-timeout 7200 \
  --poll-interval 10
```

### 筛选输入文件

`--include` 和 `--exclude` 使用逗号分隔的 glob 模式，匹配输入目录下的 POSIX 相对路径。
候选文件仍限定为 `.pyc`：

```bash
pylingual-web-batch run ./input -o ./output \
  --include "app/**/*.pyc,core/**/*.pyc" \
  --exclude "**/test_*.pyc"
```

### 恢复任务

只恢复状态文件中已有的可恢复任务，不创建新的上传：

```bash
pylingual-web-batch resume \
  --state ./.pylingual-state.json \
  --input ./input \
  --output ./output
```

如果状态文件中保存了输入和输出路径，也可以只提供状态文件：

```bash
pylingual-web-batch resume --state ./.pylingual-state.json
```

### 查看状态

`status` 只读取本地状态，不访问 pylingual API：

```bash
pylingual-web-batch status \
  --state ./.pylingual-state.json \
  --input ./input \
  --output ./output
```

### JSONL 日志

```bash
pylingual-web-batch run ./input -o ./output --log-format jsonl
```

## 断点续跑与死任务保护

每次上传成功后，程序会立即把服务端 `identifier` 写入版本化 JSON 状态文件。

如果本地轮询达到 `--poll-timeout`：

1. 不会重新上传
2. 不会丢弃服务端任务
3. 保存任务的 `identifier` 和最后状态
4. 下次运行继续轮询原任务

因此，本地进程超时不会把仍在 pylingual 服务端运行的任务变成“死任务”。

状态文件每次更新都采用临时文件加原子替换，避免进程中断产生半写入文件。

## 队列控制

队列门控只限制**新上传任务**，不会阻止已有任务恢复轮询。

默认队列上限为 `10`：

- 真实任务位置 `< 10`：允许继续提交新的任务
- 真实任务位置 `>= 10`：停止本批次新的上传
- 已有 `identifier` 的恢复任务：绕过新上传门控
- `--jobs` 默认是 `1`，可通过参数调整本地并发

程序使用运行锁，避免相同状态文件被多个进程同时处理。

## 任务状态

| 状态 | 含义 | 下一次运行 |
|---|---|---|
| `pending` | 正在轮询 | 继续使用原 identifier |
| `uploaded` | 已上传，尚未完成 | 继续轮询 |
| `timeout` | 本地轮询超时 | 继续使用原 identifier |
| `done` | 已获取并写入源码 | 输出存在时跳过 |
| `decompiler_error` | 服务端返回永久失败 | 默认跳过，`--reupload` 才重试 |
| `upload_fail` | 上传未完成 | 下一次运行可重新尝试 |
| `empty` | 服务端完成但未返回源码 | 继续恢复或显式重传 |
| `skipped` | 已有输出文件 | 默认跳过 |

只有显式使用 `--reupload`，才会重新尝试已有输出或永久反编译失败的任务。

## Python API

```python
from pathlib import Path

from pylingual_web_batch import BatchConfig, BatchDecompiler

config = BatchConfig(
    input_dir=Path("./input"),
    output_dir=Path("./output"),
    concurrency=1,
    queue_limit=10,
    poll_timeout=7200,
    poll_interval=10,
)

summary = BatchDecompiler(config).run()
print(summary)
```

更多示例：

- [`examples/basic.py`](examples/basic.py)
- [`examples/configuration.toml`](examples/configuration.toml)

## API 地址和请求行为

默认 API 地址：

```text
https://api.pylingual.io
```

使用的接口：

```text
POST /upload
GET  /get_progress?identifier=...
GET  /view_chimera?identifier=...
```

客户端会处理网络超时、连接错误、HTTP 429 和 HTTP 5xx，并使用有限次数的退避重试。
明确的参数错误不会无限重试。

## 安全与授权

`.pyc` 文件可能包含敏感、专有或未公开的代码。请注意：

- 只上传你有权处理的文件
- 遵守 pylingual 的服务条款和适用法律
- 将 API `identifier` 视为任务凭据，不要公开
- 不要提交 `.pyc`、状态文件、反编译源码、日志、密钥或 API Token
- 不要把生产环境状态文件放入公开 GitHub 仓库

本项目只提供批量客户端，不替你判断输入文件是否有权处理。

## 开发与验证

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
python -m build
```

测试使用 `httpx.MockTransport` 或 fake client，不会访问真实 pylingual 服务。

GitHub Actions 会在 Python 3.10 至 3.13 上运行测试并构建安装包。推送 `v*` 标签时，
GitHub Release workflow 会构建并上传 wheel 和源码包；项目目前不自动发布到 PyPI。

## 相关链接

- GitHub 仓库：<https://github.com/ttungx/pylingual-web-batch>
- 最新 Release：<https://github.com/ttungx/pylingual-web-batch/releases>
- 英文文档：[`README.md`](README.md)

## 许可证

本项目采用 MIT License，详见 [`LICENSE`](LICENSE)。
