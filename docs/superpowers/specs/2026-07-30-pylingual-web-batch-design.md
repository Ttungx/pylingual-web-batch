# pylingual-web-batch 设计规格

日期：2026-07-30
目标仓库：`ttungx/pylingual-web-batch`

## 1. 目标

将现有批量 pylingual Web API 反编译能力整理为独立 Python 包，提供：

- `.pyc` 文件递归发现
- pylingual Web API 上传、轮询、结果获取
- 并发控制
- 队列位置门控
- 断点续跑
- 超时后保留任务 identifier，避免产生死任务
- 永久失败识别
- CLI 与 Python API
- 可测试、可构建、可发布的 GitHub 开源项目

包不包含 TradingAgents 业务代码、当前项目 `.pyc`、反编译结果、服务器凭据或运行状态。

## 2. 非目标

- 不实现 Web 控制台
- 不实现服务端任务取消（pylingual API 当前协议未提供可靠取消接口）
- 不保证 pylingual 服务端长期可用
- 不绕过 pylingual 服务条款、认证或访问限制
- 不把工具绑定到某个业务项目

## 3. 用户接口

### CLI

```bash
pylingual-web-batch run INPUT -o OUTPUT
pylingual-web-batch resume --state .pylingual-state.json
pylingual-web-batch status --state .pylingual-state.json
```

主要选项：

- `--jobs`：本地并发，默认 1
- `--queue-limit`：新任务队列位置上限，默认 10
- `--poll-timeout`：单任务本地轮询上限，默认 7200 秒
- `--poll-interval`：轮询间隔，默认 10 秒
- `--state`：状态文件路径
- `--lock-file`：运行锁路径
- `--reupload`：明确要求重新上传
- `--include` / `--exclude`：输入文件筛选
- `--log-format`：text 或 jsonl

### Python API

```python
from pylingual_web_batch import BatchConfig, BatchDecompiler

config = BatchConfig(
    input_dir="input",
    output_dir="output",
    concurrency=1,
    queue_limit=10,
)
summary = BatchDecompiler(config).run()
```

## 4. 模块边界

```text
src/pylingual_web_batch/
├── api.py        HTTP 客户端、响应模型转换
├── batch.py      批次编排、并发、任务生命周期
├── cli.py        命令行解析与退出码
├── discovery.py  输入发现、相对路径和输出映射
├── errors.py     可分类异常
├── locking.py    跨平台运行锁
├── models.py     配置、任务、状态、统计模型
├── queue.py      新上传队列门控
└── state.py      原子状态读写和状态迁移
```

每个模块只暴露稳定接口；API 客户端不负责文件发现，状态层不负责网络请求，批次编排不拼接 HTTP 请求。

## 5. 任务生命周期

1. 发现输入 `.pyc`，生成 `input_path / output_path / relative_key`。
2. 输出文件已存在且未使用 `--reupload`：标记 skipped。
3. 状态中有可恢复 identifier 且状态为 pending、uploaded、timeout、empty：直接恢复轮询。
4. 新任务上传前调用队列门控。
5. 上传成功后立即原子保存 identifier 和任务状态。
6. 上传真实任务后读取其 position；position 达到上限时停止后续新上传。
7. 轮询至 done、永久失败或本地 deadline。
8. done 后获取源码，校验响应结构，原子写入输出文件，标记 done。
9. 本地 timeout：保存 identifier 和 last position，下一批次继续轮询，禁止自动重新上传。
10. `success=false` 且无有效 stage：标记 decompiler_error，不再自动轮询。
11. 网络失败按错误类型退避重试；不因一次 HTTP 错误丢弃 identifier。

队列门控只限制新上传，不限制已经存在 identifier 的恢复任务。

## 6. 状态文件

使用版本化 JSON，写入临时文件后替换目标文件，避免进程中断造成半文件：

```json
{
  "version": 1,
  "tasks": {
    "pkg/module.pyc": {
      "identifier": "...",
      "status": "pending|uploaded|timeout|done|decompiler_error|upload_fail|empty",
      "attempts": 1,
      "last_stage": "waiting_for_decompiler(pos=3)",
      "last_pos": 3,
      "error": null,
      "updated_at": "..."
    }
  }
}
```

读取损坏状态文件时返回明确错误，不覆盖原文件；CLI 给出恢复建议。

identifier 视为服务端任务凭据：普通日志只显示前缀，状态文件由用户自行保护，文档不上传状态文件。

## 7. API 客户端

默认端点：`https://api.pylingual.io`，可由配置覆盖。

- `POST /upload`：multipart 字段 `file`、`fileName`
- `GET /get_progress?identifier=...`
- `GET /view_chimera?identifier=...`

客户端要求：

- 使用标准 multipart 编码
- 配置 User-Agent、Origin、Referer
- 检查 HTTP 状态码
- 解析并验证 JSON 响应
- 区分网络错误、HTTP 429/5xx、上传拒绝、服务端永久失败
- 对 429、5xx、网络超时指数退避；不重试明确的 4xx 参数错误
- 使用 connect/read 总超时，不能让单次请求无限挂起

## 8. 并发和锁

`--jobs` 控制本地任务并发，默认 1，禁止无意中扩大远端队列。

运行锁默认使用输入批次关联的 lock 文件；同一状态文件已有进程运行时，CLI 退出并给出提示。

锁实现按平台隔离：Unix 使用 `fcntl`，Windows 使用 `msvcrt` 或等效独占创建；锁释放必须位于 finally。

## 9. 输出与安全

- 创建父目录后以 UTF-8 写入 Python 源码
- 先写临时文件，再替换目标文件
- 默认不覆盖已有输出
- 日志不打印完整 identifier、请求体或源码内容
- 不提交 `.pyc`、状态文件、日志、输出目录、密钥
- `.env.example` 只放非敏感配置名

## 10. 测试门禁

单元测试覆盖：

- 发现和路径映射
- 状态原子写入、损坏处理、状态迁移
- 上传成功后立即保存 identifier
- timeout 后恢复原 identifier
- `decompiler_error` 不重复上传
- 缓存命中 done
- 队列 `< limit` 连续提交，`>= limit` 停止新上传
- resume 不经过新上传门控
- 429、5xx、超时重试
- 文件锁冲突
- CLI 参数和退出码

集成测试使用 mock HTTP server，不访问真实 pylingual 服务。发布前运行：

```text
pytest
ruff check .
python -m build
```

## 11. 发布

GitHub 仓库：`https://github.com/ttungx/pylingual-web-batch`

仓库包含 MIT License、README、CHANGELOG、示例、测试和 GitHub Actions。
Actions 至少执行测试、lint、构建 wheel/sdist。GitHub 发布后可选择同步到 PyPI；本次设计不把 PyPI 凭据写入仓库。

## 12. 成功标准

- 新环境可通过 `pip install` 安装
- 一条 CLI 命令可处理目录内 `.pyc`
- 中断后重新执行不会重新上传已有 identifier
- 队列达到限制后不再产生新上传
- 永久失败不会被当作超时反复轮询
- mock 测试覆盖核心生命周期并通过
- GitHub Actions 通过
- 仓库不包含业务项目文件、凭据、状态和反编译产物
