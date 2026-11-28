# Experiments

For the fixed-room Office48 A/B object comparison and the B-group resident SAM
3D run, see [the protocol](office48-sam3d-ab/README.md). It has a separate frozen
input and scoring workflow; its seed candidates are not unattended `EXP-*` agent
runs or evidence of a completed baseline comparison.

The [Task 4 scale audit](task4-scale-audit/README.md) documents coordinate
conventions and records controlled Office48 object and TUM trajectory checks.

Each run of the real2sim agent is one experiment, with one folder `EXP-NNN-slug/`
holding `record.md` (from `TEMPLATE.md`) and `env.json`. `index.csv` lists one
row per experiment.

## Layout

```text
agentic-real2sim/
├── third_party/aha-3d/  dev checkout (submodule). Write code and new skills here. Never run experiments here.
├── exp-baseline/        frozen at commit 82f4b11 (original AHa-3D); git-ignored
├── exp-ours-vN/         frozen at your tag ours-vN (create when a version is ready)
├── experiments/         records (this folder)
├── docker/              experiment container image
└── scripts/             helper scripts
```

The `exp-*` folders are git worktrees of `third_party/aha-3d`. Their `.runtime/`
(models and venvs) and `external/` are symlinks into the submodule. Reference
videos are copied in, so each experiment's inputs stay fixed.

Records named `EXP-NNN-slug/` are single unattended Codex runs made with this
protocol. They and `index.csv` are git-ignored and shared through the team's
Google Drive, together with large run outputs (`worktree_outputs/`, about 2 GB
per run) and raw Codex logs (`codex.jsonl`). Only the protocol, `TEMPLATE.md`
and the `bin/` shim are tracked. Folders with other names
(`office48-baseline-001/`, `sam3d-startup-profile/`) follow their own README.

`scripts/new_experiment.sh` numbers a new record after the `EXP-*` folders it
finds locally, so copy the existing records from the Drive into `experiments/`
before opening a new one. EXP-001 to EXP-003 (TUM RGB-D office baseline) were
made before this repository existed; paths inside them refer to an older layout.

## Protocol

1. **Freeze the condition.** Tag the commit you want to test in
   `third_party/aha-3d` (`git tag ours-v1`), then run
   `scripts/make_exp_worktree.sh exp-ours-v1 ours-v1`.
   Never edit files inside an `exp-*` worktree. If something needs fixing, fix it
   in `third_party/aha-3d`, tag again, and make a new worktree.
2. **Reset the worktree, then open the record before the run.** Outputs are
   git-ignored, so a worktree can look clean while still holding the previous
   run's `runs/`, `scenes/`, `deliveries/`, `tasks/` and `gallery/` files, and the
   agent will resume from them. Move them into the previous record's
   `worktree_outputs/` first (as in EXP-002/EXP-003), until
   `git status --porcelain --ignored` lists only `.runtime`, `external/*`,
   `kimodo_blender/env.local.sh` and `references/*`. Then open the record:
   `scripts/new_experiment.sh exp-baseline baseline-dorm references/dorm01.mp4`.
   This captures the commit, clean status, Codex version and model, GPU, Blender
   and the input hash.
3. **Run the agent unattended in the experiment container.** Save the prompt as
   `experiments/EXP-NNN-slug/prompt.txt`, then:
   ```bash
   E=experiments/EXP-NNN-slug
   scripts/exp_container.sh exp-baseline codex exec --dangerously-bypass-approvals-and-sandbox \
     --json -o "$PWD/$E/last_message.txt" "$(cat $E/prompt.txt)" > $E/codex.jsonl 2> $E/codex.stderr
   ```
   Build the image once with `docker build --build-arg USERNAME=$(id -un) --build-arg USER_UID=$(id -u) -t aha3d-exp:latest docker/`. The
   container (`scripts/exp_container.sh`) mounts host runtimes read-only at their
   original paths and makes only the worktree, its git metadata, `experiments/`,
   `~/.codex` and the Hugging Face cache writable. No approval prompts occur, so
   no human input enters the run. The measurement shim is already on PATH; it
   drops `--ephemeral` from the reviewer's `codex exec` calls so their sessions
   are saved and can be costed. Nothing else changes.
   Use the same prompt wording across conditions; only the scene id and video
   should change. Paste the exact prompt into §4 of the record.

   Why a container: on the host, Codex's `workspace-write` sandbox has no network
   (Blender `-b` then hangs on exit, and the reviewer cannot reach the API) and
   no GPU device (`/dev/dxg` is not exposed), so a sandboxed run needs a human to
   approve every Blender, GPU and reviewer command (EXP-001). Blender renders with
   software GL (llvmpipe) on both host and container; Cycles sees the GPU via CUDA.
4. **Record the process:** note your subscription usage before and after, every
   approval and intervention, and anything surprising.
5. **Afterwards:** run `scripts/codex_session_stats.py` on the main session **and**
   every reviewer session created during the run (all `rollout-*.jsonl` files in
   that time window; reviewer sessions have originator `codex_exec`). It prints
   tokens and an **API-equivalent cost** at OpenAI standard list prices. This is a
   comparison metric, not what the subscription actually charges. Then run
   `bash tools/indoor acceptance check SCENE TASK` (inside the worktree), fill
   §6–§9, and update the `index.csv` row.

## Comparability rules

- Use the same input video, prompt template, model, reasoning effort, approval
  mode and hardware across the conditions being compared.
- Agent runs vary from run to run. Plan for at least 2–3 runs per condition on
  the key comparisons.
- AHa-3D's image reviewer runs `codex exec --ephemeral`. Without the shim its
  calls leave no session log, and the cost is undercounted (as in EXP-001).
- Prices live in `PRICES` in `scripts/codex_session_stats.py`, with a source URL
  and the date checked. Keep the same price table for every condition you
  compare. If you change the model, add its price first.
- Keep raw Codex session logs. They count toward the course's AI-use documentation.
