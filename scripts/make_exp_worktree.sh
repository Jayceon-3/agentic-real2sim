#!/usr/bin/env bash
# Create a frozen experiment checkout of aha-3d at a given commit/tag.
# Usage: scripts/make_exp_worktree.sh NAME GIT_REF
#   e.g. scripts/make_exp_worktree.sh exp-baseline 82f4b11
#        scripts/make_exp_worktree.sh exp-ours-v1 ours-v1
# The dev checkout is the third_party/aha-3d submodule. Shares its heavy model
# runtimes via symlinks; copies (not links) the reference videos so each
# experiment's inputs stay fixed.
set -euo pipefail
PROJ="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
DEV="$PROJ/third_party/aha-3d"
NAME="${1:?experiment worktree name, e.g. exp-baseline}"
REF="${2:?git ref (tag/commit) to freeze, e.g. 82f4b11}"
WT="$PROJ/$NAME"

if [[ ! -d "$WT" ]]; then
  git -C "$DEV" worktree add --detach "$WT" "$REF"
fi

# A symlinked .runtime is not matched by the repo's `.runtime/` (directory-only)
# ignore rule; exclude it once in the shared info/exclude so `git status` stays clean.
EXCLUDE="$(git -C "$DEV" rev-parse --path-format=absolute --git-common-dir)/info/exclude"
mkdir -p "$(dirname "$EXCLUDE")"
grep -qxF '/.runtime' "$EXCLUDE" 2>/dev/null || echo '/.runtime' >> "$EXCLUDE"

ln -sfn "$DEV/.runtime" "$WT/.runtime"
mkdir -p "$WT/external"
for repo in Pi3 sam3; do
  [[ -e "$DEV/external/$repo" ]] && ln -sfn "$DEV/external/$repo" "$WT/external/$repo"
done
cp "$DEV/kimodo_blender/env.local.sh" "$WT/kimodo_blender/env.local.sh"
mkdir -p "$WT/references"
cp -n "$DEV"/references/tum_* "$WT/references/" 2>/dev/null || true

# Both runtimes have aha3d installed editable from the dev checkout; env.sh puts
# this worktree's src first on PYTHONPATH. Verify that the frozen code wins.
got="$(cd "$WT" && source kimodo_blender/env.sh && python -c 'import aha3d, pathlib; print(pathlib.Path(aha3d.__file__).resolve().parents[2])')"
[[ "$got" == "$WT" ]] || { echo "aha3d resolves to $got, not $WT" >&2; exit 1; }
mesh="$(cd "$WT" && source kimodo_blender/env.sh && "$PI3X_MESH_PY" -c 'import aha3d, pathlib; print(pathlib.Path(aha3d.__file__).resolve().parents[2])')"
[[ "$mesh" == "$WT" ]] || { echo "mesh env aha3d resolves to $mesh, not $WT" >&2; exit 1; }

echo "Ready: $WT at $(git -C "$WT" rev-parse --short HEAD) (aha3d imports from this worktree)"
git -C "$WT" status --short
