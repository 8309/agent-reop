.PHONY: help setup-env install-local check test demo-repoops demo-repoops-manual demo-repoops-langchain demo-repoops-langchain-codex demo-repoops-langchain-claude demo-repoops-langchain-gemini

help:
	@printf "Targets:\n"
	@printf "  make setup-env      Create/update the micromamba environment and install local packages\n"
	@printf "  make install-local  Reinstall both editable packages into the environment\n"
	@printf "  make check          Validate scaffold files and syntax\n"
	@printf "  make test           Run standard-library smoke tests\n"
	@printf "  make demo-repoops   Run the manual RepoOps CLI\n"
	@printf "  make demo-repoops-langchain Run the LangChain learning demo\n"
	@printf "  make demo-repoops-langchain-codex Run the LangChain demo with Codex CLI as the provider\n"
	@printf "  make demo-repoops-langchain-claude Run the LangChain demo with Claude Code CLI as the provider\n"
	@printf "  make demo-repoops-langchain-gemini Run the LangChain demo with Gemini CLI as the provider\n"

setup-env:
	@./scripts/setup_micromamba.sh

install-local:
	@./scripts/run_in_mamba.sh pip install -e projects/shared -e projects/repoops

check:
	@./scripts/run_in_mamba.sh python scripts/verify_repo.py
	@./scripts/run_in_mamba.sh python -c "import repoops, portfolio_shared"
	@./scripts/run_in_mamba.sh python -m compileall projects scripts >/dev/null

test:
	@./scripts/run_in_mamba.sh python scripts/run_tests.py

demo-repoops: demo-repoops-manual

demo-repoops-manual:
	@./scripts/run_in_mamba.sh python -m repoops.cli \
		--repo . \
		--issue examples/issues/sample_bug.md \
		--dry-run

demo-repoops-langchain:
	@./scripts/run_in_mamba.sh python -m repoops.langchain_demo \
		--repo . \
		--issue examples/issues/sample_bug.md \
		--dry-run

demo-repoops-langchain-codex:
	@./scripts/run_in_mamba.sh python -m repoops.langchain_demo \
		--repo . \
		--issue examples/issues/sample_bug.md \
		--dry-run \
		--provider codex-cli

demo-repoops-langchain-claude:
	@./scripts/run_in_mamba.sh python -m repoops.langchain_demo \
		--repo . \
		--issue examples/issues/sample_bug.md \
		--dry-run \
		--provider claude-code-cli

demo-repoops-langchain-gemini:
	@./scripts/run_in_mamba.sh python -m repoops.langchain_demo \
		--repo . \
		--issue examples/issues/sample_bug.md \
		--dry-run \
		--provider gemini-cli
