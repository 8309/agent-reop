# RepoOps - 项目概述

## 一句话介绍

一个 Agent 工作流框架，能把 GitHub Issue 自动变成经过测试验证的 PR——从问题理解、方案规划、代码生成、到测试验证全链路自动化。

## 项目动机

现有的 AI 编程工具（Copilot、Cursor）擅长代码补全，但缺少**端到端闭环**能力。我想探索：Agent 范式能否把 "理解需求 → 规划方案 → 改代码 → 验证 → 输出 PR" 这个完整流程串起来，并且保证可靠性。

## 核心流程

```
issue.md → 解析 → 仓库扫描 → LLM 规划 → LLM 生成编辑 → 安全写入 → 测试验证 → 输出制品
                                                              ↑              ↓
                                                            回滚  ←──  失败重试(×2)
```

## 技术栈

| 层次 | 选型 | 原因 |
|------|------|------|
| 语言 | Python 3.12+ | 生态最好，LangChain 原生支持 |
| LLM 编排 | LangChain + Pydantic | 结构化 chain、schema 校验、可插拔 |
| 数据模型 | Pydantic v2 | 严格类型、JSON Schema 自动生成给 LLM |
| LLM 后端 | Gemini CLI / Claude Code CLI / Codex CLI / deterministic | 多 Provider 对比，抽象基类统一接口 |
| 测试验证 | subprocess 调 `make test` | 语言无关，任何项目都可以 |

## 输出制品（每次运行自动生成）

| 文件 | 内容 |
|------|------|
| `plan.json` | 完整执行 payload，包含中间结果 |
| `patch.diff` | 统一 diff 格式的代码变更 |
| `pr_draft.md` | 自动生成的 PR 描述 |
| `test_report.json` | 测试执行结果和指标 |

## 项目结构

```
agent-program/
├── projects/repoops/          # 主工作流
│   └── src/repoops/
│       ├── langchain_demo.py   # LLM 驱动的主 pipeline（~400行）
│       ├── write_actions.py    # 编辑应用、备份回滚、diff 生成
│       ├── read_only_tools.py  # 仓库扫描（list_files, read_file, code_search）
│       ├── cli.py              # 入口 + 验证 + 制品持久化
│       ├── base_cli_provider.py        # LLM Provider 抽象基类
│       ├── gemini_cli_provider.py      # Gemini 后端
│       ├── claude_code_cli_provider.py # Claude Code 后端
│       └── codex_cli_provider.py       # Codex 后端
├── projects/shared/            # 共享契约（issue 解析、payload 构建）
├── examples/demo-repo/         # 端到端测试用的 demo 仓库
│   ├── src/mathlib.py          # 有意留 bug 的数学库
│   ├── tests/test_mathlib.py   # 包含一个故意失败的测试
│   └── issue.md                # 给 RepoOps 处理的 issue
└── docs/
    ├── pipeline.mmd            # Mermaid 流程图源码
    └── pipeline.png            # 生成的流程图
```
