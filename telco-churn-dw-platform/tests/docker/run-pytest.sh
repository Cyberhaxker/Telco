#!/usr/bin/env bash
# Install the monorepo packages from the mounted source and run pytest.
set -euo pipefail
cd /repo
for pkg in libs/common_py services/*/ ml; do
  if [[ -f "$pkg/pyproject.toml" ]]; then pip install -q --no-deps -e "$pkg"; fi
done
exec python -m pytest "$@"
