# Agentic Real2Sim — Initial Exploration and Five-Person Task Allocation

With limited time and compute, investigate these five questions before building a complete system:

1. **SAM 3D Objects Integration:** Can SAM 3D Objects be reliably integrated into AHa-3D?
2. **Geometric Verifier:** Can a geometric verifier provide more stable, reproducible feedback than VLM-only judgment?
3. **Frame Selection:** How much does input-frame selection affect SAM 3D reconstruction quality?
4. **Scale Audit & Coordinate Alignment:** Are scale and coordinate alignment major sources of system error?
5. **Verification-guided Agent Feedback & Repair:** Can an agent use structured verification feedback to improve reconstruction results?

**Shared principles:** Reuse the existing AHa-3D Blender scene, camera parameters and segmentation. Start with one video and one or two static furniture objects. Minimize full-pipeline reruns and SAM 3D inference calls.

## 2. Task Allocation Overview

| Person | Research direction | First-stage deliverables | Compute needs |
|---|---|---|---|
| 1 | SAM 3D Objects Integration | Image + Mask → SAM 3D → Blender demo; inference cost records | Relatively low |
| 2 | Geometric Verifier | Multi-view mask IoU; initial failure detection | Relatively low |
| 3 | Frame Selection for SAM 3D | Candidate-frame scoring script; comparisons using a few input frames | Low; GPU needed for validation |
| 4 | Scale Audit & Coordinate Alignment | Coordinate/scale error analysis; at least one correction experiment | Very low |
| 5 | Verification-guided Agent Feedback & Repair | Structured feedback interface; repair and re-verification loop | Low; higher for full reconstruction |

> Person numbers identify tasks and do not assign specific team members.

## 3. Detailed Tasks by Direction

### Direction 1: SAM 3D Objects Integration

**Research Question:** Can SAM 3D Objects be reliably integrated into the existing AHa-3D pipeline?

**Main tasks**

- Run SAM 3D Objects inference and confirm the image, object-mask and output-mesh interfaces and formats.
- Generate meshes for one or two static furniture objects and import them into the existing AHa-3D Blender scene.
- Check mesh scale, orientation, position and compatibility with the scene coordinate system; collaborate with Direction 4 on alignment.
- Measure model initialization, inference and mesh export/import times; record peak GPU memory and failures.
- Make an initial comparison of quality and cost against procedural modeling.

**First-stage deliverables**

- A reproducible `Image + Mask → SAM 3D → Blender` demo.
- At least one object successfully imported and placed in the scene.
- A brief performance breakdown and integration failure log.

**Scope:** Establish integration feasibility first. Exclude model training, CUDA optimization and batch reconstruction.

### Direction 2: Geometric Verifier

**Research Question:** Can geometric verification provide more reliable and reproducible feedback than VLM-based visual judgment?

**Main tasks**

- Render segmentation masks of the target object in Blender using AHa-3D camera poses.
- Align source and rendered masks and compute multi-view silhouette IoU.
- Repeat verification on a small set of correct and incorrect reconstructions to assess numerical stability.
- Introduce controlled scale, translation and other errors to test verifier sensitivity.
- Design structured failure fields such as `silhouette_mismatch`, `scale_mismatch` and `position_mismatch`; report specific error types only when supported by the metrics.

**First-stage deliverables**

- A script taking a Blender object, camera poses and source masks and returning per-view and aggregate IoU.
- Comparisons of normal and deliberately incorrect reconstructions.
- Initial failure detection rules and a feedback format.

**Scope:** Prioritize silhouette IoU and defer complex physics simulation. IoU alone cannot reliably distinguish every error cause.

### Direction 3: Frame Selection for SAM 3D

**Research Question:** How does source-frame selection affect SAM 3D reconstruction quality?

**Main tasks**

- Extract several candidate frames of the target object from the same video.
- Compute inexpensive features such as object visibility, mask area, occlusion, sharpness and viewpoint, where available.
- Design a simple frame-ranking heuristic and compare it with random or fixed-frame selection.
- Run SAM 3D on only two or three representative frames to control compute costs.
- Compare mesh quality for the same object under a fixed evaluation protocol and investigate relationships between selection features and quality.

**First-stage deliverables**

- Candidate-frame extraction, scoring and ranking scripts.
- Reconstruction comparisons using a few input frames of the same object.
- Preliminary observations about input factors that may affect reconstruction.

**Scope:** Do not run SAM 3D on every candidate frame. Small-sample findings are exploratory evidence only.

### Direction 4: Scale Audit & Coordinate Alignment

**Research Question:** Are scale inconsistencies and coordinate transformations major sources of reconstruction error?

**Main tasks**

- Trace transformations between camera coordinates, world coordinates, reference geometry, SAM 3D meshes and Blender objects.
- Check for duplicated or omitted unit, axis, transformation-matrix and object-scale conversions.
- Revisit the preliminary observation of approximately 8% scene-scale error and distinguish global scale error from object-level alignment error.
- Estimate scale factors using trustworthy reference geometry or depth information.
- Implement a scale/translation correction for one controlled case and quantify error before and after correction.

**First-stage deliverables**

- A brief analysis of coordinate transformations and potential error sources.
- An audit script reporting object dimensions, scale and position.
- At least one calibration or position-correction demo.

**Scope:** Identify root causes first; do not assume global rescaling resolves every error. Share alignment conventions with Direction 1.

### Direction 5: Verification-guided Agent Feedback & Repair

**Research Question:** Can an agent use structured verification feedback to improve reconstruction quality through repair or tool switching?

**Main tasks**

- Document the existing AHa-3D visual feedback, judgment and modification workflow.
- Define a shared structured feedback interface with scores, error types, optional repair actions and confidence/validity information.
- Implement repair logic with simulated feedback before Direction 2's real verifier is available.
- Start with rule-based scale, position or rotation adjustments and cap repair attempts.
- Connect the verifier to complete a `Verification → Repair → Re-verification` loop.
- If time permits, test procedural ↔ SAM 3D tool switching/fallback against no-feedback and fixed-retry policies.

**First-stage deliverables**

- A structured feedback schema and minimal repair interface.
- A reproducible repair and re-verification demo.
- Before/after comparisons of quality, latency and call counts.

**Scope:** Start with deterministic rules rather than complex multi-round agent planning.

## 4. Collaboration and Dependencies

- **Shared assets:** Everyone uses the same Blender scene, camera poses, object masks, object IDs and coordinate conventions.
- **Directions 1 ↔ 4:** Jointly debug SAM 3D mesh import and coordinate/scale alignment.
- **Directions 2 → 5:** The verifier supplies machine-readable scores and feedback; Direction 5 can develop in parallel using mock feedback.
- **Directions 3 ↔ 1:** Frame selection supplies candidates; Direction 1 centrally runs a small number of SAM 3D requests to avoid duplicate model loads and computation.
- **Directions 2 ↔ 4:** Use deliberately injected scale/position errors to test detection and correction.
- **Shared evaluation:** Fix the scene, cameras, target objects and run budget. Record mask IoU, depth error where available, latency, GPU memory, failure types and retries. Keep development/repair views separate from held-out evaluation views.
