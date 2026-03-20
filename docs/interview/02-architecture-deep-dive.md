# RepoOps - 架构深入讲解

## 三个关键设计决策

面试中重点讲这三个决策，每个都体现了工程思考：

### 决策 1：用 LangChain + Pydantic 结构化输出，而非自由文本

**问题**：LLM 返回自由文本不可靠，格式不稳定，下游无法解析。

**方案**：
- 用 Pydantic 定义严格的数据模型（`PlanDraftModel`、`EditPlanModel`）
- Pydantic 的 `model_json_schema()` 自动生成 JSON Schema，注入到 prompt 的 `{format_instructions}` 中
- LangChain 的 `PydanticOutputParser` 做解析 + 校验
- 所有 model 都设置 `extra="forbid"`，LLM 多返回一个字段直接报错

**代码示例**（`langchain_demo.py`）：
```python
class FileEditModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(description="Relative path to the file to edit")
    original_snippet: str = Field(description="Existing code snippet")
    proposed_snippet: str = Field(description="Proposed replacement code")

# Schema 自动注入 prompt
edit_parser = PydanticOutputParser(pydantic_object=EditPlanModel)
edit_input = {
    "format_instructions": edit_parser.get_format_instructions(),
    ...
}
```

**面试话术**：
> 我用 Pydantic 定义了编辑的数据模型，让 LLM 返回严格的 JSON 而不是自由文本。这样下游代码可以直接拿到类型安全的对象，不需要做任何正则解析。

---

### 决策 2：代码修改用精确字符串匹配，而非 AST 或 diff

**问题**：怎么把 LLM 生成的代码变更可靠地应用到文件？

**方案**：
- LLM 返回 `original_snippet`（原文）+ `proposed_snippet`（替换）
- 应用时用 `str.replace(original_snippet, proposed_snippet, 1)` 做精确替换
- 把"精确匹配"的负担转移到 prompt 工程上

**代码示例**（`write_actions.py:326-347`）：
```python
def apply_edit_to_file(repo_root: str, proposal: FileEditProposal) -> bool:
    content = file_path.read_text(encoding="utf-8")
    if original not in content:
        return False  # 精确匹配失败
    new_content = content.replace(original, proposal["proposed_snippet"], 1)
    file_path.write_text(new_content, encoding="utf-8")
    return True
```

**为什么不用 AST？**
- 语言无关——Python、JS、Go 都能用同一套逻辑
- 实现极其简单，总共 20 行代码
- 把准确性问题转化为 prompt 工程问题，而 prompt 是可迭代的

**面试话术**：
> 我选了最简单的方案：精确字符串替换。这看起来粗暴，但它语言无关、实现简单。准确性的问题我通过 prompt 工程解决——后面会讲这个踩坑过程。

---

### 决策 3：闭环重试机制——让 Agent 从自己的错误中学习

**问题**：LLM 生成的代码不一定能通过测试，怎么办？

**方案**：
```
备份原始文件 → 应用编辑 → 跑测试
                              ↓
                          测试通过？ → 是 → 完成
                              ↓ 否
                          回滚文件 → 把测试输出喂回 LLM → 重新生成编辑 → 再试
                          （最多重试 2 次）
```

**代码示例**（`langchain_demo.py:556-604`）：
```python
for attempt in range(1 + MAX_RETRIES):
    backups = backup_repo_files(repo, edit_proposals) if can_retry else {}
    payload = apply_write_action(payload)
    payload = run_validation(payload)

    if passed or not can_retry or attempt == MAX_RETRIES:
        break

    # 失败：回滚 → 重新生成
    rollback_repo_files(repo, backups)
    new_edits = retry_edit_proposals(
        provider=..., test_output=test_output, ...
    )
```

**重试 prompt 的关键设计**（`RETRY_EDIT_PROMPT_TEMPLATE`）：
- 包含上一次的编辑内容（让 LLM 知道自己做了什么）
- 包含测试失败输出（让 LLM 知道哪里错了）
- 包含回滚后的文件内容（确保 original_snippet 依然精确）

**面试话术**：
> 我加了闭环重试：测试失败后回滚文件，把测试输出和之前的编辑一起喂回 LLM，让它分析失败原因并修正。这不是简单的 retry，而是给 LLM 反馈信号让它自我纠正。

---

## Pipeline 两步 Chain 设计

用 LangChain 串联两个 chain，而不是一步到位：

```
Chain 1 (Planning):   PromptTemplate → LLM → PydanticOutputParser → PlanDraftModel
Chain 2 (Editing):    PromptTemplate → LLM → PydanticOutputParser → EditPlanModel
```

**为什么拆成两步？**
1. 关注点分离：规划和编辑是不同的认知任务
2. 可观测性：中间产物 `plan_outline` 可以人工审查
3. Chain 2 的 prompt 依赖 Chain 1 的输出（plan_summary）

## 多 Provider 抽象

通过抽象基类 `BaseCLIProvider` 统一不同 LLM 后端：

```python
# 每个 provider 实现 invoke_json()
class GeminiCLIProvider(BaseCLIProvider):
    def invoke_json(self, prompt_text, output_schema) -> str: ...

class ClaudeCodeCLIProvider(BaseCLIProvider):
    def invoke_json(self, prompt_text, output_schema) -> str: ...
```

用 `RunnableLambda` 把 CLI provider 包装成 LangChain Runnable，统一进 chain：
```python
def build_planner_runnable(provider, repo, issue_text):
    if provider == "gemini-cli":
        gemini = GeminiCLIProvider(repo)
        return RunnableLambda(lambda pv: gemini.invoke_json(...)), [...]
```

**面试话术**：
> 我用工厂模式 + 抽象基类让不同 LLM 后端可插拔。实际测试中 Gemini 表现最稳定，Claude Code 也可以但需要特殊环境变量处理，Codex 太慢被搁置了。
