# Preparation evidence and limitations

## Evidence available in this checkout

- Source video and cached RGB frames, input frame/time manifest, full reference
  geometry, structural cameras, mesh manifest and reference build report exist.
- Initial source-view contact sheet and frame-152 Blender test render were viewed
  by the agent in the preceding conversation. The render shows the supplied
  office whitebox with no obvious missing geometry or missing-texture appearance;
  this verifies that example's GUI rendering, not new reconstruction quality.
- The reference contact sheet supports proceeding with investigation/authoring:
  room/opening outlines are useful, while furniture, glass and chandelier surfaces
  are visibly approximate. Full structural/object acceptance remains pending.
- No local new authored room, integrated video or final acceptance exists.

## Historical remote preparation (human-provided reports)

Great Lakes account: eecs442f26_class; Pi3X GPU job: 65406875; NVIDIA A40.
The local manifests bind source, mesh and camera identities, but full original
remote job logs, pip freezes and Pi3X run_report.json have not been downloaded.
Remote measurements below are transcribed from the conversation, not newly run.

| Item | Reported result |
| --- | --- |
| Python | 3.11.5 |
| PyTorch | 2.7.1+cu128 |
| Pi3 source commit | 9fa3ddb3f8d53041f8b2738df404f62223bbaa7b |
| Pi3X weight revision | bb1deea4d7423de5b30691739cb451a3f57dc1d5 |
| Pi3X weight SHA256 | 69972d6e1c4492cb4d737a84fe940e357087d81c52f5c9b7c160b49c1f41669a |
| Pi3X peak allocated GPU memory | 13.716594219207764 GiB (not total device usage) |
| Pi3X load / inference / total | 52.8656 / 27.0137 / 98.4051 seconds |
| SAM3 source commit | 660a5e9e1b8b4c02c0ad97229b88a09a6e4ff5b7 |
| SAM3 weight revision | 3c879f39826c281e95690f02c7821c4de09afae7 |
| SAM3 image inference | Single-frame GPU smoke passed; full-frame reference subsequently built |
| Open3D runtime | pip check and REFERENCE_MESH_IMPORT_OK reported passed |
| Blender GUI | Windows Blender 5.2.1 LTS shown in user screenshot; example frame 152 rendered |

SAM3 installation initially failed at pip check because decord 0.6.0 metadata
declares cp36 although imports passed on Python 3.11. The advised workaround pins
SAM3-environment pip to 24.1.2, avoiding newer installed-wheel tag validation.
Successful later preparation does not independently establish the exact installed
pip version; download pip/version inventories before making a stronger claim.
No model dependency or upstream source change is established by this workaround.

## Agent, review and cost accounting

Agent: this Codex conversation. Exact backend model ID and sampling/reasoning
settings are not reliably available to the recording process: unknown. Do not
infer them from an interface label or upstream's advertised model. The task prompt
v1 supplements the existing conversation and system/developer/repository rules;
it is not a complete independently replayable transcript. Upstream agent-contract
and workflow identities are included in the lock.

The human installed environments, obtained gated access, downloaded weights and
video, ran the supplied cluster commands, transferred artifacts, and rendered the
upstream example through the GUI. These are preparation interventions. Agent
scene-authoring time, total preparation compute cost, token counts and API cost
are unknown. Record preparation costs separately from subsequent authoring.

This is an assisted workflow reproduction on an upstream demonstration scene,
with prior exposure to its supplied authored result. It is not a blinded or
held-out evaluation, nor an exact reproduction of the upstream agent/model.
Monocular geometry, camera fits, source-overlay consistency and floor residuals
are not independent ground truth or measured metric accuracy.

## Remaining work

1. Record executable access to local Blender for agent scripts.
2. Declare upstream scene scope and ownership before reconstruction writes.
3. Review floor/upright and source coverage; retain unsupported scale/hidden bounds.
4. Author a new room, furnishings and materials through the original tool workflow.
5. Validate source views, placement, full video timing/decoding and saved scene.
6. Select the exact final artifacts and report failures and available costs.
