"""Check the direction of the Sim(3) scale and holdout ownership."""

import importlib.util
from pathlib import Path
import unittest

import numpy as np


SCRIPT = Path(__file__).resolve().parents[1] / "eval_pi3x_tum_ate.py"
SPEC = importlib.util.spec_from_file_location("eval_pi3x_tum_ate", SCRIPT)
EVALUATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATOR)


class TrajectoryScaleTests(unittest.TestCase):
    def test_fit_excludes_holdout_and_returns_the_correction_factor(self):
        centers = np.array([[0, 0, 0], [1, 1, 0], [2, 0, 1], [2, 3, 1], [4, 1, 0], [5, 3, 2]])
        timestamps = np.arange(10, 16)
        truth = np.column_stack((timestamps, centers))
        frames = []
        for index, (x, y, z) in enumerate(centers):
            pose = np.eye(4)
            pose[:3, 3] = 1.08 * np.array([-y, x, z]) + [10, 2, -3]
            frames.append({"source_frame": index, "c2w": pose.tolist()})
        mapping = [{"video_frame": index, "tum_timestamp": float(timestamps[index])}
                   for index in reversed(range(len(centers)))]

        result = EVALUATOR.evaluate({"frames": frames}, {"frames": mapping}, truth, holdout_every=2)

        self.assertEqual(result["fit_source_frames"], [0, 2, 4])
        self.assertEqual(result["evaluation_source_frames"], [1, 3, 5])
        self.assertAlmostEqual(result["gt_from_estimated_scale"], 1 / 1.08)
        self.assertAlmostEqual(result["estimated_scale_error_percent"], 8.0)
        self.assertGreater(result["rigid_ate"]["rmse_m"], 0.1)
        self.assertLess(result["similarity_ate"]["rmse_m"], 1e-12)

    def test_collinear_fit_has_an_explicit_error(self):
        centers = np.array([[0, 0, 0], [1, 1, 1], [2, 2, 2]])
        with self.assertRaisesRegex(ValueError, "non-collinear"):
            EVALUATOR.fit_transform(centers, centers)


if __name__ == "__main__":
    unittest.main()
