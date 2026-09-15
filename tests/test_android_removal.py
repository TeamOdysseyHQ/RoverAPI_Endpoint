"""Ensure application startup no longer imports or mounts the Android listener."""
import ast
from pathlib import Path
import unittest


class AndroidRemovalTests(unittest.TestCase):
    def test_router_has_no_android_import_or_route(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / 'app/api/router.py').read_text(encoding='utf-8'))
        self.assertNotIn('android', ast.dump(tree).lower())
        self.assertFalse((root / 'app/api/others/android_sensors.py').exists())


if __name__ == '__main__':
    unittest.main()
