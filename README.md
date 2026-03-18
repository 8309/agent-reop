# Agentic Portfolio Lab

This repository is intentionally trimmed down to the current working core:

- `projects/repoops`: the active `RepoOps` workflow
- `projects/shared`: the shared contract used by every `RepoOps` execution path

The current focus is one clear loop:

`issue.md -> structured plan -> runs/<run_id>/plan.json`

Inside `RepoOps`, you can exercise that loop through:

- the manual baseline CLI
- a `LangChain` learning path
- local CLI-backed providers: `Codex CLI`, `Claude Code CLI`, and `Gemini CLI`

## Repo Layout

```text
.
├── examples/
│   └── issues/
├── projects/
│   ├── repoops/
│   └── shared/
├── scripts/
├── Makefile
├── environment.yml
└── README.md
```

## Quickstart

Create or update the `micromamba` environment first. This also installs the local editable packages so the `repoops` modules are immediately runnable:

```bash
make setup-env
```

Then run the basic repository checks:

```bash
make check
make test
```

Run the core demos:

```bash
make demo-repoops
make demo-repoops-langchain
make demo-repoops-langchain-codex
make demo-repoops-langchain-claude
make demo-repoops-langchain-gemini
```

## Configuration

Project-level settings that should stay in version control:

- `AGENTS.md` — agent behavior rules
- `environment.yml` — micromamba environment spec
- `Makefile` — standard targets
- `.codex/config.toml` — Codex project defaults
