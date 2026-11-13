from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from app.api.navigation.camera import MultiCameraManager


class CameraDiscoveryTests(unittest.TestCase):
    def test_discovery_probes_each_physical_device_once_in_parallel_and_returns_capabilities(self):
        manager = MultiCameraManager()
        formats = [{'fourcc': 'MJPG', 'resolutions': [{'width': 1280, 'height': 720, 'frame_rates': [60]}]}]
        barrier = threading.Barrier(2)
        def capabilities(name):
            barrier.wait(timeout=1)
            return {'formats': formats}
        devices = {'kreo': '/dev/named-kreo', 'science': '/dev/named-science'}
        aliases = {'/dev/named-kreo': '/dev/video0', '/dev/named-science': '/dev/video2'}
        with patch('app.api.navigation.camera.CAMERA_DEVICES', devices), patch('app.api.navigation.camera.Path.glob', return_value=[Path('/dev/video0'), Path('/dev/video2')]), patch('app.api.navigation.camera.os.path.exists', return_value=True), patch('app.api.navigation.camera.os.path.realpath', side_effect=lambda p: aliases.get(p, p)), patch.object(manager, 'get_supported_resolutions', side_effect=capabilities) as probe:
            cameras = manager.detect_cameras()
        self.assertEqual(probe.call_count, 2)
        self.assertEqual([camera['name'] for camera in cameras], ['kreo', 'science'])
        for camera in cameras:
            self.assertEqual(camera['formats'], formats)
            self.assertEqual(camera['default_fps'], 60)
            self.assertFalse(camera['camera']['active'])
