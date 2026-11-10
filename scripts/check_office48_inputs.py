"""Check the initial office48 experiment lock without ML/Blender dependencies."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / "experiments/office48-baseline-001/inputs.lock.json").read_text())
    errors = []
    for entry in lock["files"]:
        path = root / entry["path"]
        if not path.is_file():
            errors.append(f"Missing: {entry['path']}")
        elif path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
            errors.append(f"Changed: {entry['path']}")
    upstream = root / "third_party/aha-3d"
    revision = subprocess.run(["git", "-C", str(upstream), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    if revision != lock["code"]["aha3d_commit"]:
        errors.append("AHa-3D commit changed")
    dirty = subprocess.run(["git", "-C", str(upstream), "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        errors.append("AHa-3D has tracked modifications; record a new code identity")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"OFFICE48_INPUT_LOCK_OK ({len(lock['files'])} files; pinned upstream clean)")
    print("Identity checks only; no geometry, video decode or scene acceptance implied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
