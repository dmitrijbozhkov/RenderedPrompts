#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd -- "${SCRIPT_DIRECTORY}/../.." && pwd)"
OUTPUT_DIRECTORY="${REPOSITORY_ROOT}/stubs/outputs"
STUBGEN_EXECUTABLE="${STUBGEN_EXECUTABLE:-stubgen}"

mkdir -p -- "${OUTPUT_DIRECTORY}"

"${STUBGEN_EXECUTABLE}" \
  --no-import \
  --include-docstrings \
  --search-path "${REPOSITORY_ROOT}/src" \
  --output "${OUTPUT_DIRECTORY}" \
  --module agent.utils.scout

# These stubs are injected as API documentation after the runtime module's
# public names have already been imported into the coding environment.
find "${OUTPUT_DIRECTORY}" -type f -name '*.pyi' -exec \
  sed -i -e '/^import /d' -e '/^from .* import /d' {} +
