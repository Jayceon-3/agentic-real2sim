#!/bin/bash
# Check the already-installed environments; do not mutate working ML runtimes.
set -eo pipefail
exec bash "$(dirname "${BASH_SOURCE[0]}")/run.sh" doctor "$@"
