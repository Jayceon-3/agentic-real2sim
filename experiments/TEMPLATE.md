# {{EXP_ID}}: {{TITLE}}

<!-- Fields marked (auto) are filled by scripts/new_experiment.sh or
     scripts/codex_session_stats.py. Fill everything else by hand. -->

## 1. Purpose

- **Question / hypothesis:**
- **Compared against:** (e.g. EXP-001 baseline)
- **Operator:**
- **Date:** {{DATE}} (auto)

## 2. Condition (the independent variable)

| Field | Value |
|---|---|
| Worktree | `{{WORKTREE}}` (auto) |
| Git ref / commit | `{{GIT_REF}}` / `{{COMMIT}}` (auto) |
| Worktree clean at start? | {{CLEAN}} (auto; must be "yes" for a valid run) |
| What differs from baseline | (e.g. "new skill sam3d-object-generation"; "none" for baseline) |
| Agent CLI / version | Codex {{CODEX_VERSION}} (auto) |
| Model / reasoning effort | {{MODEL}} / {{EFFORT}} (auto, from ~/.codex/config.toml) |
| Approval mode / sandbox | (e.g. on-request / workspace-write) |
| Repair budget given | |

## 3. Input

| Field | Value |
|---|---|
| Video | `{{VIDEO}}` |
| SHA-256 | `{{VIDEO_SHA}}` (auto) |
| Resolution / fps / frames | |
| Source + license | |
| Reused reference cache | (path, or "fresh build_reference") |
| Pi3X frame tier | 32 |

## 4. Exact prompt given to the agent

Paste verbatim, including follow-up messages and your answers to intake questions.

```text

```

## 5. Hardware

{{HARDWARE}} (auto)

## 6. Process metrics

| Metric | Value |
|---|---|
| Codex session log | `~/.codex/sessions/.../rollout-....jsonl` |
| Start → end (UTC) | (codex_session_stats.py) |
| Wall time (min) | (codex_session_stats.py) |
| Tool calls | (codex_session_stats.py) |
| Context compactions | (codex_session_stats.py) |
| Tokens in (cached) / out | (codex_session_stats.py) |
| Reviewer sessions included | (count of codex_exec rollouts; needs the shim) |
| API-equivalent cost (USD) | (codex_session_stats.py total; main + reviewer sessions) |
| Subscription usage before → after | (read from ChatGPT usage page) |
| Scene revisions produced | (count runs/SCENE/.../vN) |
| Formal VLM review rounds / verdicts | (count *review_attempt*.log, layout_judgment.json) |
| Human approvals clicked | |
| Human interventions (beyond approvals) | (count; describe each in §9) |

Reviewer calls run `codex exec --ephemeral`. They are only counted when Codex was
launched with `experiments/bin` on PATH (see experiments/README.md).

## 7. Outcome

- **Acceptance check** (`bash tools/indoor acceptance check SCENE TASK`):
  `status` = , `completion_permitted` = , blockers:
- **Agent's final state:** (accepted & selected / blocked / failed / gave up)
- **Final candidate:** `runs/...`
- **Key renders:** (paths)

## 8. Our evaluation

### 8.1 Object inventory (expected from the source vs. modeled)

| Object | In source | Modeled | Notes (shape, position, scale) |
|---|---|---|---|
| | | | |

### 8.2 Visual fidelity (1 = unrecognizable, 5 = matches source)

| Aspect | Score | Notes |
|---|---|---|
| Room structure / layout | | |
| Major furniture shape | | |
| Placement / orientation | | |
| Scale | | |
| Overall | | |

### 8.3 Quantitative metrics

| Metric | Value | Script |
|---|---|---|
| Camera ATE vs GT (cm) / scale error | | `scripts/eval_pi3x_tum_ate.py` |
| Rendered depth error vs GT depth | | (TBD) |
| Placement check errors / warnings | | `tools/indoor check-placement` |

## 9. Observations, failures, interventions

- 

## 10. AI-use log (course requirement)

- Codex session: (path; copy under `ai_usage/` when sharing)
- Other assistants used to plan/analyze this run:
