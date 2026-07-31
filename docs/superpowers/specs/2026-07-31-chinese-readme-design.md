# 中文 README 设计

## 目标

为 `ttungx/pylingual-web-batch` 增加完整简体中文版说明，不改变包行为、CLI、依赖或发布流程。

## 文件

- `README.md`：英文默认首页，顶部加入 `README.zh-CN.md` 链接
- `README.zh-CN.md`：完整简体中文文档，顶部加入英文链接

## 内容范围

中文版与当前英文 README 保持同等信息覆盖：

1. 项目简介
2. 安装方式
3. 快速开始
4. 输入发现和筛选
5. `run`、`resume`、`status` 命令
6. 断点续跑、队列门控、失败状态
7. Python API
8. 安全与授权
9. 开发、测试、构建
10. GitHub Actions 和 Release 说明

命令、参数、状态值、路径、URL、代码块和示例保持可复制，不翻译标识符。

## 交叉链接

两份文档顶部使用：

```md
[English](README.md) | [简体中文](README.zh-CN.md)
```

英文 README 保持默认 GitHub 首页，不改 `pyproject.toml` 的 readme 配置。

## 验收

- 中文文件覆盖英文文档的全部用户操作和安全限制
- Markdown 链接有效
- 命令示例与当前 CLI 参数一致
- `git diff --check` 通过
- 不产生包代码或测试改动
