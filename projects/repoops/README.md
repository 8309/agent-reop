# RepoOps

`RepoOps` is the active project in this repository.

## Goal

Turn an issue description into a controlled agent workflow:

- inspect repository context
- generate a structured plan
- keep writes behind approval
- save artifacts for review

## Current Status

The manual `RepoOps` CLI now uses read-only repository tools before it writes `plan.json`. Each run captures a `repo_context` block with:

- a lightweight file inventory
- previews of key files
- search hits for planning-relevant symbols

The `LangChain` learning demo now receives that same `repo_context` in its prompt, so the manual CLI and provider-backed flow can reason from the same repository evidence.

## Demo

```bash
make demo-repoops
```

If you prefer to learn top-down from `LangChain` first, start here instead:

```bash
make demo-repoops-langchain
```

That learning demo keeps the same `issue -> structured plan` goal, but shows the chain as:

- `PromptTemplate`
- `Runnable`
- `PydanticOutputParser`

If you want to keep the same chain shape but use your local `Codex CLI` login as the model backend, run:

```bash
make demo-repoops-langchain-codex
```

If you want to use your local `Claude Code CLI` login instead, run:

```bash
make demo-repoops-langchain-claude
```

If you want to use your local `Gemini CLI` login instead, run:

```bash
make demo-repoops-langchain-gemini
```

## Next Milestones

1. Add approval-gated write actions.
2. Expand the run artifact set beyond `plan.json`.
3. Tighten the planner prompts and provider behavior for the local CLI backends.
4. Start turning repo context into actionable edit proposals.
