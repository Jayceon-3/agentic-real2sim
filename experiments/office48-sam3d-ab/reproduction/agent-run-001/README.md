# Agent run 001: historical script snapshots

These are the exact scripts and implementation snapshots preserved from the
November 26, 2026 six-candidate B continuation. They are historical evidence,
not a portable command-line package. Original files remain unchanged under
`outputs/office48-sam3d-ab/agent-run-001/source/`.

To reconstruct the historical directory layout, copy these source files to that
original source directory first. Most scripts derive the repository root from
that location and use a fixed run path. The log writer also derives its output
location from its original directory. Do not execute these archive copies in
place. A new experiment needs a new run directory and explicit path changes;
do not overwrite the frozen results.

Dependencies include Python, NumPy, Pillow, SciPy, a C++ compiler, configured
Blender/Cycles, the upstream AHa-3D checkout, and the source resources identified
by the frozen lock and provenance. Compile `raster.cpp` into `raster.so` in the
restored source directory before placement search. Runtime binaries, geometry
caches, source inputs, GLBs and Blender scenes are distributed separately.

`align-attempt-001.py` and earlier implementation snapshots preserve abandoned
attempts. `align.py`, `blender_stage.py`, `blender_batch.py`, `inspection.py`,
`collect.py`, and `final_report.py` record the selected workflow. Consult the
original operation log for sequencing, failures and corrections. Evaluation
results must not be used to retune the selected placements.
