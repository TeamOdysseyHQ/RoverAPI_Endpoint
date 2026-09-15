"""Hardware-free regression tests for the camera resolutions method.

Compile the actual manager class from its AST so these tests can run on Windows
without importing Linux-only fcntl or initializing FastAPI/storage/OpenCV.
Only the external device-existence and v4l2-ctl calls are mocked. This is not a
full route integration test.
"""

import ast
from pathlib import Path
import re
import subprocess
from typing import Optional
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class CameraResolutionTests(unittest.TestCase):
    def setUp(self):
        source_path = Path(__file__).resolve().parents[1] / "app/api/navigation/camera.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        manager = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MultiCameraManager")
        self.run = Mock()
        self.exists = Mock(return_value=True)
        namespace = {
            "os": SimpleNamespace(path=SimpleNamespace(exists=self.exists)),
            "subprocess": SimpleNamespace(run=self.run, TimeoutExpired=subprocess.TimeoutExpired),
            "re": re,
            "Optional": Optional,
            "cv2": SimpleNamespace(VideoCapture=object),
            "CAMERA_DEVICES": {"science": "/dev/camera-science"},
        }
        exec(compile(ast.Module(body=[manager], type_ignores=[]), str(source_path), "exec"), namespace)
        self.manager = namespace["MultiCameraManager"]()

    def test_restored_method_parses_formats_and_deduplicates_sizes(self):
        self.run.return_value = SimpleNamespace(returncode=0, stdout="""
            [0]: 'MJPG' (Motion-JPEG, compressed)
                Size: Discrete 1280x720
                Size: Discrete 1280x720
                Size: Discrete 640x480
            [1]: 'YUYV' (YUYV 4:2:2)
                Size: Discrete 320x240
        """)
        result = self.manager.get_supported_resolutions("science")
        self.assertTrue(result["success"])
        self.assertEqual([f["fourcc"] for f in result["formats"]], ["MJPG", "YUYV"])
        self.assertEqual(result["formats"][0]["resolutions"], [
            {"width": 1280, "height": 720}, {"width": 640, "height": 480},
        ])
        self.run.assert_called_once_with(
            ["v4l2-ctl", "-d", "/dev/camera-science", "--list-formats-ext"],
            capture_output=True, text=True, timeout=5,
        )

    def test_generic_video_device_is_supported(self):
        self.run.return_value = SimpleNamespace(returncode=1, stdout="")
        result = self.manager.get_supported_resolutions("video3")
        self.assertTrue(result["success"])
        self.assertEqual(self.run.call_args.args[0][2], "/dev/video3")

    def test_frame_rates_stay_attached_to_the_correct_resolution_and_format(self):
        self.run.return_value = SimpleNamespace(returncode=0, stdout="""
            [0]: 'MJPG' (Motion-JPEG)
                Size: Discrete 1280x720
                    Interval: Discrete 0.017s (60.000 fps)
                    Interval: Discrete 0.033s (30.000 fps)
                Size: Discrete 1920x1080
                    Interval: Discrete 0.067s (15.000 fps)
            [1]: 'YUYV' (YUYV 4:2:2)
                Size: Discrete 1280x720
                    Interval: Discrete 0.100s (10.000 fps)
        """)
        formats = self.manager.get_supported_resolutions("science")["formats"]
        self.assertEqual(formats[0]["resolutions"][0]["frame_rates"], [60, 30])
        self.assertEqual(formats[0]["resolutions"][1]["frame_rates"], [15])
        self.assertEqual(formats[1]["resolutions"][0]["frame_rates"], [10])

    def test_missing_and_invalid_devices_do_not_run_a_probe(self):
        self.exists.return_value = False
        for name in ("science", "unknown", "video-invalid"):
            with self.subTest(name=name):
                self.assertFalse(self.manager.get_supported_resolutions(name)["success"])
        self.run.assert_not_called()

    def test_probe_failures_preserve_fallback_response(self):
        failures = [FileNotFoundError(), subprocess.TimeoutExpired("v4l2-ctl", 5), RuntimeError("probe failed")]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                self.run.side_effect = failure
                result = self.manager.get_supported_resolutions("science")
                self.assertTrue(result["success"])
                self.assertEqual(result["formats"][0]["fourcc"], "PRESET")
                self.assertIn({"width": 1280, "height": 720}, result["formats"][0]["resolutions"])

    def test_empty_output_uses_fallback(self):
        self.run.return_value = SimpleNamespace(returncode=0, stdout="")
        result = self.manager.get_supported_resolutions("science")
        self.assertTrue(result["success"])
        self.assertEqual(result["formats"][0]["fourcc"], "PRESET")


if __name__ == "__main__":
    unittest.main()
