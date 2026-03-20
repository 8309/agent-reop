# RepoOps - 开发过程中的问题与解决方案

这是面试中最加分的部分。每个问题都展示了工程判断力。

---

## 问题 1：Gemini 生成的代码片段无法精确匹配（最重要，必讲）

### 背景
代码修改的核心逻辑是精确字符串替换：LLM 返回 `original_snippet`，系统在文件中找到这段代码并替换成 `proposed_snippet`。

### 现象
用 Gemini 跑 demo-repo 的 divide-by-zero 修复任务时，编辑应用全部静默失败。`apply_edit_to_file()` 返回 `False`，但没有报错，文件没有被修改，测试结果和修复前一样。

### 根因分析
对比 Gemini 返回的 `original_snippet` 和文件实际内容：

```python
# Gemini 生成的 original_snippet:
def divide(a, b):
    return a / b

# 文件中的实际代码:
def divide(a: float, b: float) -> float:
    """Return a / b.
    BUG: does not handle division by zero — raises an unhandled
    ZeroDivisionError instead of returning a clear error.
    """
    return a / b
```

差异：
1. **丢了类型注解**：`(a, b)` vs `(a: float, b: float) -> float`
2. **丢了 docstring**：Gemini 跳过了整个文档字符串
3. **导入路径错误**：测试文件中 Gemini 写 `mathlib.divide(10, 2)` 但实际是 `divide(10, 2)`

### 决策过程
面对这个问题有两个方向：

| 方案 | 优点 | 缺点 |
|------|------|------|
| 模糊匹配（difflib/fuzzy） | 容忍 LLM 的不精确 | 增加复杂度，可能误匹配，治标不治本 |
| **改进 Prompt（选择这个）** | 简单，从源头解决 | 依赖 LLM 遵守指令 |

### 解决方案
在 `EDIT_PROMPT_TEMPLATE` 中加入 CRITICAL RULES：

```python
EDIT_PROMPT_TEMPLATE = (
    "You are a RepoOps code editor.\n"
    "...\n\n"
    "CRITICAL RULES:\n"
    "- `original_snippet` must be copied VERBATIM from the file contents below.\n"
    "  Include type annotations, docstrings, comments, and whitespace exactly as they appear.\n"
    "  The snippet will be used for exact string matching — even one wrong character will fail.\n"
    "- Do NOT invent code that is not in the file. Copy-paste from the file contents below.\n\n"
    "...\n"
    "File contents:\n{file_contents}\n\n"  # 把完整文件内容放进 prompt
    "..."
)
```

关键改进：
1. **明确告知后果**："even one wrong character will fail"
2. **给出具体指令**："Include type annotations, docstrings, comments"
3. **把完整文件内容放进 prompt**：让 LLM 有明确的复制来源

### 结果
- 修复前：snippet 匹配成功率 **0%**（所有编辑静默失败）
- 修复后：snippet 匹配成功率 **100%**，Gemini 完整保留了类型注解和 docstring

### 面试话术
> 这个问题教会我一件事：**不要用工程复杂度去补偿 LLM 的行为，而要用 prompt 去约束 LLM 的行为**。模糊匹配看起来更"工程化"，但它是在容忍问题而不是解决问题。改 prompt 更简单，效果更好，而且可以持续迭代。

---

## 问题 2：编辑失败时静默吞掉错误

### 现象
`apply_edit_to_file()` 返回 `False` 但没有任何日志或报错。用户看到的是"测试没通过"，但根本不知道是编辑没有被应用。

### 根因
原始代码只是简单地返回 `True/False`，没有在 payload 中记录失败信息。

### 解决方案
在 `apply_write_action()` 中增加 `failed_edits` 追踪：

```python
failed_edits: list[dict[str, str]] = []
for ep in _get_edit_proposals(payload):
    if apply_edit_to_file(repo_root, ep):
        applied.append(...)
    else:
        failed_edits.append({
            "path": ep["path"],
            "reason": "snippet not found in file"
        })
if failed_edits:
    payload["failed_edits"] = failed_edits
```

### 面试话术
> 静默失败是 Agent 系统最危险的 bug——系统以为自己做了修改，但文件根本没变。我加了 failed_edits 追踪，让每次失败都有记录，这样调试时可以立刻定位到 snippet 匹配问题。

---

## 问题 3：测试 RepoOps 时用自身代码做目标，导致自举问题

### 现象
最初用 RepoOps 自己的代码仓库做测试目标。问题：
1. 仓库太大，LLM context window 放不下所有文件
2. RepoOps 修改自己的代码可能破坏正在运行的流程
3. 无法设计一个确定性会失败的测试用例

### 解决方案
创建 `examples/demo-repo/`——一个极小的 Python 项目，专为测试设计：

```python
# src/mathlib.py — 有意留 bug
def divide(a: float, b: float) -> float:
    """BUG: does not handle division by zero"""
    return a / b  # 没有零值检查

# tests/test_mathlib.py — 故意失败的测试
def test_divide_by_zero():
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        divide(1, 0)  # 会抛 ZeroDivisionError 而非 ValueError
```

配套 `issue.md` 描述问题，`Makefile` 提供 `make test` 命令。

### 设计思路
- **小**：只有两个源文件，LLM 不会被无关代码干扰
- **确定性**：bug 和失败测试都是精心设计的，结果可预测
- **端到端**：issue → 修复 → 全部测试通过，完整验证整个 pipeline

### 面试话术
> 我做了一个专用的 demo 仓库来做端到端测试。关键是它足够小、bug 是确定性的、测试结果可预测。这让我能快速迭代 pipeline 逻辑，而不用担心仓库规模或自举问题。

---

## 问题 4：闭环重试的状态管理

### 挑战
重试循环涉及多个状态变化：备份 → 写入 → 测试 → 回滚 → 重新生成 → 再写入。如果状态管理不对，可能导致：
- 回滚到错误的版本
- 重试时用了修改后的文件内容（而非原始内容）
- Payload 中的 edit_proposals 没更新

### 关键设计
```python
for attempt in range(1 + MAX_RETRIES):
    # 1. 每次循环开始时重新备份（不是只备份一次）
    backups = backup_repo_files(repo, edit_proposals)

    # 2. 应用并验证
    payload = apply_write_action(payload)
    payload = run_validation(payload)

    if passed:
        break

    # 3. 回滚到备份状态
    rollback_repo_files(repo, backups)

    # 4. 回滚后重新读取文件内容给 LLM
    file_contents = collect_edit_context(repo, repo_context)

    # 5. 用回滚后的文件内容（不是修改后的）生成新编辑
    new_edits = retry_edit_proposals(..., file_contents=file_contents)

    # 6. 更新 payload 并重新 prepare
    payload["edit_proposals"] = [ep.model_dump() for ep in new_edits]
    payload = prepare_write_action(payload)
```

### 关键点
- **回滚后重新读文件**：确保 LLM 看到的是原始代码，`original_snippet` 才能精确匹配
- **保留重试历史**：`retry_history` 记录每次尝试的编辑和测试结果，方便调试
- **备份粒度是文件级**：只备份被编辑的文件，不是整个仓库

### 面试话术
> 闭环重试看起来简单，但状态管理是核心难点。最关键的一点：回滚后必须重新读取文件内容再给 LLM，否则 LLM 会基于修改后的代码生成 original_snippet，导致第二次编辑也匹配失败。

---

## 问题 5：多 LLM Provider 的差异处理

### 差异对比

| Provider | 特性 | 遇到的问题 |
|----------|------|-----------|
| **Gemini CLI** | 速度快，JSON 输出稳定 | snippet 不精确（已通过 prompt 解决） |
| **Claude Code CLI** | 质量高 | 需要 `unset CLAUDECODE` 否则环境变量冲突 |
| **Codex CLI** | 有代码执行能力 | 太慢（分钟级），被搁置 |
| **Deterministic** | 无 LLM，关键词匹配 | 不能真正修复 bug，但保证测试可重复 |

### Deterministic 模式的设计意义
- 单元测试不依赖 LLM API（不花钱、不 flaky）
- 验证 pipeline 流程本身的正确性，隔离 LLM 质量问题
- CI 中用 deterministic，开发时用真实 LLM

### 面试话术
> 我做了 deterministic 模式：不调 LLM，用关键词匹配生成编辑。这样单元测试不依赖外部 API，CI 跑起来既快又稳定。真正的 LLM 测试放在端到端测试里，用 demo-repo 验证。

---

## 总结：问题解决的方法论

这些问题展示了一个共同的思维模式：

1. **优先简单方案**：精确匹配 > AST 解析，改 prompt > 模糊匹配
2. **从源头解决**：约束 LLM 输出 > 容忍 LLM 错误
3. **可观测性优先**：静默失败 → failed_edits 追踪，每步有制品输出
4. **关注点分离**：demo-repo 隔离测试，deterministic 模式隔离 LLM
