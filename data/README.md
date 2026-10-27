# Data

Store downloaded videos and extracted frames under `data/local/` (ignored by Git).
Do not commit datasets or credentials.

Before a run, record the dataset/source URL, sequence identifier, usage terms,
download instructions, file checksum, and any clipping or conversion steps in the
experiment record. Preserve the mapping to original frame indices and timestamps.

The static baseline consumes RGB video. Keep ground-truth depth and camera poses
separate from reconstruction inputs and document their use in evaluation.
