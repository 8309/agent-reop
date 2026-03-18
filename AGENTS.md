# Agent Rules

## Environment Management

- Use `micromamba` for all project environments on this machine.
- The default environment name for this repository is `agentic-portfolio`.
- Do not create `.venv` environments for this repo.
- Do not install project dependencies with bare system `pip`.
- Before running project Python commands, ensure the environment exists with:

```bash
make setup-env
```

- Run project Python commands through `micromamba`, either with:

```bash
micromamba run -n agentic-portfolio <command>
```

or via the repository `make` targets.

## RepoOps

- Keep every `RepoOps` execution path on the same shared contract.
- Use `projects/shared` for anything the manual CLI and `LangChain` flow must agree on.
