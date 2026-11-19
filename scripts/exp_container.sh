#!/usr/bin/env bash
# Run a command inside the experiment container, with one exp-* worktree writable.
# Usage: scripts/exp_container.sh WORKTREE_NAME [COMMAND...]
#   e.g. scripts/exp_container.sh exp-baseline bash
#        scripts/exp_container.sh exp-baseline codex exec --dangerously-bypass-approvals-and-sandbox "..."
#
# Build the image once: docker build --build-arg USERNAME=$(id -un) --build-arg USER_UID=$(id -u) -t aha3d-exp:latest docker/
# Writable inside the container: the chosen worktree, its git metadata, experiments/,
# ~/.codex (auth + session logs) and the Hugging Face cache. Everything else that is
# mounted is read-only; the rest of the host filesystem is not visible at all.
# The measurement shim (experiments/bin) is first on PATH.
set -euo pipefail
PROJ="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
NAME="${1:?worktree name, e.g. exp-baseline}"; shift
WT="$PROJ/$NAME"
[[ -d "$WT" && "$NAME" == exp-* ]] || { echo "No exp-* worktree at $WT" >&2; exit 1; }
DEV="$PROJ/third_party/aha-3d"
# Worktree metadata lives in the submodule's git dir (under the superproject's .git/modules).
GIT_COMMON="$(git -C "$DEV" rev-parse --path-format=absolute --git-common-dir)"
H="$HOME"
NVM_BIN="$(dirname -- "$(command -v codex)")"
NVM_ROOT="$(cd -- "$NVM_BIN/../.." && pwd -P)"
BLENDER_DIR="$(dirname -- "$(source "$DEV/kimodo_blender/env.local.sh" && echo "$BLENDER_BIN")")"
IMAGE="${EXP_IMAGE:-aha3d-exp:latest}"

tty=(); [[ -t 0 && -t 1 ]] && tty=(-it)
# Optional read-only inputs; skipped when absent so Docker does not create them as root.
extra=()
for d in outputs data; do
  [[ -d "$PROJ/$d" ]] && extra+=(-v "$PROJ/$d:$PROJ/$d:ro")
done
# The submodule's .runtime and external/* may be symlinks to an existing install
# elsewhere; mount their real targets read-only at the same paths.
for link in "$DEV/.runtime" "$DEV"/external/*; do
  if [[ -L "$link" ]]; then
    real="$(readlink -f -- "$link")"
    [[ -e "$real" ]] && extra+=(-v "$real:$real:ro")
  fi
done
# seccomp/apparmor unconfined: AHa-3D's image reviewer runs a nested
# `codex exec --sandbox read-only`, whose bubblewrap sandbox needs to create user
# namespaces, which Docker's default profiles block. Isolation still comes from the mounts.
exec docker run --rm "${tty[@]}" --gpus all --init \
  --security-opt seccomp=unconfined --security-opt apparmor=unconfined \
  --user "$(id -u):$(id -g)" --hostname "aha3d-$NAME" \
  -e HOME="$H" -e TERM="${TERM:-xterm}" \
  -e PATH="$PROJ/experiments/bin:$NVM_BIN:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
  -e CODEX_SHIM_LOG="$PROJ/experiments/shim.log" \
  -v "$DEV:$DEV:ro" \
  -v "$GIT_COMMON:$GIT_COMMON" \
  -v "$WT:$WT" \
  -v "$PROJ/experiments:$PROJ/experiments" \
  "${extra[@]}" \
  -v "$PROJ/scripts:$PROJ/scripts:ro" \
  -v "$BLENDER_DIR:$BLENDER_DIR:ro" \
  -v "$H/.local/share/uv:$H/.local/share/uv:ro" \
  -v "$NVM_ROOT:$NVM_ROOT:ro" \
  -v "$H/.codex:$H/.codex" \
  -v "$H/.cache/huggingface:$H/.cache/huggingface" \
  -w "$WT" "$IMAGE" "${@:-bash}"
