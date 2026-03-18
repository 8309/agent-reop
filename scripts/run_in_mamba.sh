#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="agentic-portfolio"

if ! command -v micromamba >/dev/null 2>&1; then
  printf "micromamba is not installed or not on PATH.\n" >&2
  exit 1
fi

if ! micromamba env list | awk '{print $1}' | grep -qx "${ENV_NAME}"; then
  printf "Micromamba environment '%s' was not found.\n" "${ENV_NAME}" >&2
  printf "Run: make setup-env\n" >&2
  exit 1
fi

exec micromamba run -n "${ENV_NAME}" "$@"

