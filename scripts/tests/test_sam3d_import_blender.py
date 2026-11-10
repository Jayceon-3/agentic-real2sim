"""Placement contract checks; real Blender import requires a separate smoke run."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('sam3d_import', ROOT / 'scripts/sam3d_objects/import_blender.py')
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


class PlacementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'placement.json'
        self.value = json.loads((ROOT / 'configs/sam3d_placement.example.json').read_text())

    def load(self):
        self.path.write_text(json.dumps(self.value))
        return importer.load_placement(self.path)

    def test_explicit_identity_contract(self):
        self.assertEqual(self.load(), self.value)

    def test_reject_ambiguous_coordinate_space_and_unknown_keys(self):
        self.value['coordinate_space'] = 'sam3d_native'
        with self.assertRaises(ValueError):
            self.load()
        self.value['coordinate_space'] = 'blender_imported_to_scene_world'
        self.value['pose'] = 'pose.json'
        with self.assertRaises(ValueError):
            self.load()

    def test_reject_invalid_transforms(self):
        for key, vector in [('scale', [1, 0, 1]), ('scale', [-1, 1, 1]),
                            ('translation_m', [float('nan'), 0, 0]),
                            ('rotation_euler_xyz_deg', [0, float('inf'), 0]),
                            ('translation_m', [True, 0, 0]), ('scale', [1, 1])]:
            with self.subTest(key=key, vector=vector):
                original = self.value[key]
                self.value[key] = vector
                with self.assertRaises(ValueError):
                    self.load()
                self.value[key] = original

    def test_required_fields_and_semantics(self):
        for key in ('scale', 'coordinate_space', 'semantic_class'):
            original = self.value.pop(key)
            with self.assertRaises(ValueError):
                self.load()
            self.value[key] = original
        self.value['semantic_class'] = '/'
        with self.assertRaises(ValueError):
            self.load()


if __name__ == '__main__':
    unittest.main()
