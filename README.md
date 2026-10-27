# Agentic Real2Sim

EECS 442 course project: verification-guided tool selection for indoor reconstruction.

We study how an agent selects and validates reconstruction tools to turn indoor
videos into editable simulation scenes.

## Current milestone

Reproduce the original AHa-3D static reconstruction baseline on one indoor RGB
video. Preserve the original modeling and verification workflow before introducing
new reconstruction tools or decision policies.

Baseline outputs should include an editable Blender scene, matched source-view
comparisons, verification and repair records, and run configuration and cost logs.
Generating reference geometry alone does not complete the baseline: an agent must
still construct and refine the Blender scene.

## Getting started

Clone this repository with its pinned upstream dependency:

```bash
git clone --recurse-submodules git@github.com:Jayceon-3/agentic-real2sim.git
cd agentic-real2sim
```

For an existing clone:

```bash
git submodule update --init --recursive
```

Follow [AHa-3D setup](third_party/aha-3d/docs/SETUP.md) and the
[static reference guide](third_party/aha-3d/docs/PI3X_GEOMETRY_REFERENCE.md).
Inspect the Static installation plan from the upstream repository root:

```bash
cd third_party/aha-3d
bash tools/setup.sh --level static --plan
```

Installation, model downloads, and reconstruction have not yet been run for this
project. The installation plan does not install the environment. Model weights
and a compatible Blender installation must be prepared separately. The original
scene-authoring workflow also requires a configured agent; record its model and
instructions for each experiment.

## Repository structure

```text
configs/         Experiment configurations
scripts/         Project setup and experiment scripts (to be implemented)
prompts/         Versioned agent instructions
experiments/     Small run records and observations
data/            Data acquisition and provenance instructions
third_party/aha-3d/  Upstream baseline pinned as a Git submodule
```

## Experiment records

For each run, record the project and AHa-3D commits, input video checksum and
frame/time mapping, agent model and prompt, environment and GPU, runtime and
available cost information, manual interventions, verification results, and
artifact locations. Retain failures and unresolved reconstruction errors.

Use RGB as the baseline reconstruction input. If RGB-D data is used, keep
ground-truth depth and poses separate for explicitly documented evaluation.

## Local data and generated artifacts

Keep source videos in `data/local/`, generated results in `outputs/`, and model
weights in ignored storage such as `checkpoints/` or the upstream runtime cache.
Document acquisition instructions and artifact locations rather than committing
large files. Store machine-specific paths in ignored `*.local.yaml` files; never
commit credentials.

## Upstream

- [AHa-3D repository](https://github.com/KevinXu02/aha-3d)
- [AHa-3D project page](https://kevinxu02.github.io/real2sim-indoor-site/)

The submodule retains upstream source and license files. Changes to its pinned
revision should be deliberate and recorded in experiment metadata.
