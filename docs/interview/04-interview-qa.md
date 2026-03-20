# RepoOps - 面试常见问题与回答

## 技术深度类

### Q: 为什么选精确字符串匹配而不是 AST 或 tree-sitter？

**回答要点**：
- 语言无关：同一套 `str.replace()` 对 Python、JS、Go 都有效，不需要为每种语言引入 parser
- 实现简单：核心逻辑只有 20 行代码（`write_actions.py:326-347`）
- 把问题转移到 prompt 工程上：prompt 是可以持续迭代的，而且迭代成本远低于维护多语言 AST
- 事实证明效果好：加了 CRITICAL RULES 后 Gemini 的匹配成功率从 0% 到 100%

**进阶回答**（如果面试官追问局限性）：
- 承认极端情况下会失败（如文件中有完全相同的代码块）
- 通过 "最小化 snippet + 足够上下文" 的 prompt 指令缓解
- 如果未来需要更强的鲁棒性，可以考虑引入 fuzzy matching 作为 fallback

---

### Q: LLM 输出格式错误怎么办？

**回答要点**：
- Pydantic model 设置 `extra="forbid"`，多一个字段直接报错
- LangChain `PydanticOutputParser` 做 JSON 解析 + schema 校验
- `format_instructions` 把完整的 JSON Schema 注入 prompt，LLM 有明确的输出规范
- 如果解析失败，当前会直接抛异常；未来可以加 retry with parsing error feedback

---

### Q: 闭环重试和简单 retry 有什么区别？

**回答要点**：
- **简单 retry**：相同输入重跑，期待随机性产生不同结果
- **闭环重试**：把失败信息（测试输出、之前的编辑）作为新的输入，让 LLM 定向修正

```
简单 retry:  prompt → LLM → 失败 → 同一个 prompt → LLM → ...
闭环 retry:  prompt → LLM → 失败 → prompt + 失败原因 + 上次编辑 → LLM → ...
```

关键区别：每次重试的 prompt 都不一样，包含了失败的上下文。

---

### Q: 怎么保证回滚的正确性？

**回答要点**：
- 备份是 apply 之前做的，保存的是原始内容
- 回滚用 `file.write_text(backup_content)` 覆盖，不是 git checkout
- 回滚后重新读文件内容给 LLM，确保 original_snippet 基于最新状态
- 备份粒度是文件级，只备份被编辑的文件

---

## 设计思考类

### Q: 和 Devin / SWE-Agent / OpenHands 的区别？

**回答要点**：
- 定位不同：RepoOps 是轻量级 pipeline，不是通用 Agent
- 重**可控性**：每步有明确的制品输出（plan.json、patch.diff），可以人工审查
- 重**可观测性**：failed_edits 追踪、retry_history 记录、test_report 保存
- 重**简单性**：核心代码 ~400 行，没有复杂的 agent loop 或 tool calling

**进阶**：
> 我认为 Agent 系统的可靠性不来自更强的模型，而来自更好的工程设计——结构化输出、闭环验证、回滚机制，这些传统软件工程的手段在 Agent 系统里同样关键。

---

### Q: 如果要生产化，你会怎么做？

**回答要点**：
1. **触发**：接 GitHub Webhook，issue 创建时自动触发 pipeline
2. **审批**：human-in-the-loop，LLM 生成 PR 但不自动合并
3. **安全**：沙箱执行测试（Docker），防止恶意代码
4. **扩展**：
   - 自动检测项目的测试命令（不硬编码 `make test`）
   - 动态调整 repo scan 策略（根据项目大小和语言）
   - 加入代码审查步骤（用另一个 LLM 审查编辑质量）
5. **监控**：成功率、重试率、token 消耗量

---

### Q: 为什么要做 deterministic 模式？

**回答要点**：
- 单元测试不依赖 LLM API：不花钱、不 flaky、CI 友好
- 隔离关注点：验证 pipeline 流程正确性 vs 验证 LLM 输出质量
- 快速开发迭代：改 pipeline 逻辑时用 deterministic 跑，秒级反馈
- 真实 LLM 测试放在端到端测试中，用 demo-repo 验证

---

## 行为面试类

### Q: 遇到最有挑战的技术问题是什么？

**回答**（用 STAR 结构）：

- **Situation**：用 Gemini 跑端到端测试，编辑全部静默失败
- **Task**：需要定位原因并修复
- **Action**：
  1. 发现 `apply_edit_to_file()` 返回 False，对比 LLM 输出和文件内容
  2. 发现 Gemini 丢了类型注解和 docstring
  3. 面对两个方案（模糊匹配 vs 改 prompt），选择了改 prompt
  4. 加了 CRITICAL RULES 强制逐字复制
  5. 同时加了 failed_edits 追踪，让这类问题不再静默
- **Result**：匹配成功率 0% → 100%，而且方案比模糊匹配更简单

---

### Q: 你从这个项目学到了什么？

**回答要点**：

1. **Prompt 工程比代码工程更重要**：在 Agent 系统中，一条好的 prompt 规则比 100 行 fallback 代码更有效
2. **可观测性是 Agent 系统的生命线**：LLM 的行为不可预测，没有日志和中间制品就无法调试
3. **简单方案优先**：精确匹配 + prompt 约束，比 AST 解析 + 模糊匹配简单一个数量级，效果反而更好
4. **测试设计很关键**：demo-repo 的设计让我能在 30 秒内验证整个 pipeline，极大加速了迭代
