#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="agentic-portfolio"
ENV_FILE="environment.yml"

if ! command -v micromamba >/dev/null 2>&1; then
  printf "micromamba is not installed or not on PATH.\n" >&2
  exit 1
fi

if micromamba env list | awk '{print $1}' | grep -qx "${ENV_NAME}"; then
  micromamba env update -y -f "${ENV_FILE}"
  printf "Updated micromamba environment: %s\n" "${ENV_NAME}"
else
  micromamba create -y -f "${ENV_FILE}"
  printf "Created micromamba environment: %s\n" "${ENV_NAME}"
fi

# Install the local editable packages so ``python -m repoops...`` works immediately after setup.
micromamba run -n "${ENV_NAME}" pip install -e projects/shared -e projects/repoops
printf "Installed editable packages into: %s\n" "${ENV_NAME}"
