#!/usr/bin/env bash
# Start an experiment record with the environment captured automatically.
# Usage: scripts/new_experiment.sh WORKTREE_NAME SLUG [VIDEO_RELATIVE_TO_WORKTREE]
#   e.g. scripts/new_experiment.sh exp-baseline baseline-dorm references/dorm01.mp4
# Creates experiments/EXP-NNN-SLUG/{record.md,env.json} and appends to experiments/index.csv.
set -euo pipefail
PROJ="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
WT="$PROJ/${1:?worktree name, e.g. exp-baseline}"
SLUG="${2:?short slug, e.g. baseline-dorm}"
VIDEO="${3:-}"
[[ -d "$WT" ]] || { echo "No worktree $WT; create it with scripts/make_exp_worktree.sh" >&2; exit 1; }

n=$(find "$PROJ/experiments" -maxdepth 1 -type d -name 'EXP-*' | wc -l)
ID=$(printf 'EXP-%03d' $((n + 1)))
DIR="$PROJ/experiments/$ID-$SLUG"
mkdir -p "$DIR"

commit=$(git -C "$WT" rev-parse HEAD)
ref=$(git -C "$WT" describe --tags --always "$commit")
if [[ -z "$(git -C "$WT" status --porcelain)" ]]; then clean=yes; else clean="NO — $(git -C "$WT" status --porcelain | wc -l) changed paths"; fi
codex_v=$(codex --version 2>/dev/null | awk '{print $2}')
model=$(sed -n 's/^model *= *"\(.*\)"/\1/p' ~/.codex/config.toml 2>/dev/null | head -1)
effort=$(sed -n 's/^model_reasoning_effort *= *"\(.*\)"/\1/p' ~/.codex/config.toml 2>/dev/null | head -1)
gpu=$(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>/dev/null | head -1)
blender=$(source "$WT/kimodo_blender/env.sh" && "$BLENDER_BIN" --version 2>/dev/null | head -1)
video_sha=""
[[ -n "$VIDEO" && -f "$WT/$VIDEO" ]] && video_sha=$(sha256sum "$WT/$VIDEO" | cut -d' ' -f1)
now=$(date -u +%Y-%m-%dT%H:%M:%SZ)

python3 - "$DIR/env.json" <<EOF
import json, sys
json.dump({"id": "$ID", "created_utc": "$now", "worktree": "$WT", "git_ref": "$ref",
           "commit": "$commit", "worktree_clean": "$clean", "codex_version": "$codex_v",
           "model": "$model", "reasoning_effort": "$effort", "gpu": "$gpu",
           "blender": "$blender", "video": "$VIDEO", "video_sha256": "$video_sha"},
          open(sys.argv[1], "w"), indent=1)
EOF

sed -e "s|{{EXP_ID}}|$ID|; s|{{TITLE}}|$SLUG|; s|{{DATE}}|$now|" \
    -e "s|{{WORKTREE}}|$WT|; s|{{GIT_REF}}|$ref|; s|{{COMMIT}}|$commit|; s|{{CLEAN}}|$clean|" \
    -e "s|{{CODEX_VERSION}}|$codex_v|; s|{{MODEL}}|$model|; s|{{EFFORT}}|$effort|" \
    -e "s|{{VIDEO}}|$VIDEO|; s|{{VIDEO_SHA}}|$video_sha|; s|{{HARDWARE}}|$gpu; $blender|" \
    "$PROJ/experiments/TEMPLATE.md" > "$DIR/record.md"

[[ -f "$PROJ/experiments/index.csv" ]] || echo "id,slug,date_utc,worktree,commit,model,video,status,acceptance,wall_min,notes" > "$PROJ/experiments/index.csv"
echo "$ID,$SLUG,$now,$(basename "$WT"),${commit:0:7},$model,$VIDEO,running,,," >> "$PROJ/experiments/index.csv"

echo "Created $DIR/record.md"
[[ "$clean" == yes ]] || echo "WARNING: worktree is not clean; this run is not a valid controlled experiment." >&2
echo "After the run: python3 scripts/codex_session_stats.py ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl"
