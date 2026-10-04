"""Hardware-free checks of the actual camera routes and capture/lifecycle locking."""
import ast
import asyncio
from concurrent.futures import ThreadPoolExecutor
import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
import threading
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'app/api/navigation/camera.py'

class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail

class CameraEndpointTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(SOURCE.read_text())
        names = {'detect_cameras', 'start_camera', 'stop_camera', 'stop_all_cameras', 'cameras_status', 'camera_status'}
        nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
        for node in nodes:
            node.decorator_list = []
        self.manager = Mock()
        self.ns = {'camera_manager': self.manager, 'CAMERA_DEVICES': {'science': '/dev/camera-science'},
                   'Optional': Optional, 'Form': lambda default: default, 'HTTPException': HTTPException, 're': __import__('re')}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), self.ns)

    def test_camera_routes_work_without_machine_specific_debug_files(self):
        self.manager.detect_cameras.return_value = [{'name': 'science'}]
        self.manager.start_camera.return_value = True
        self.manager.get_camera_status.return_value = {'active': True}
        self.assertEqual(self.ns['detect_cameras']()['count'], 1)
        self.assertEqual(self.ns['start_camera']('science')['status'], 'ok')
        self.assertEqual(self.ns['camera_status']('science')['camera']['active'], True)
        self.assertEqual(self.ns['stop_camera']('science')['status'], 'ok')
        self.assertEqual(self.ns['stop_all_cameras']()['status'], 'ok')
        self.assertTrue(all(not inspect.iscoroutinefunction(self.ns[n]) for n in
                            ('detect_cameras', 'start_camera', 'stop_camera', 'cameras_status')))

    def test_invalid_camera_validation_and_request_shape_are_preserved(self):
        with self.assertRaises(HTTPException) as invalid:
            self.ns['start_camera']('not-a-camera')
        self.assertEqual(invalid.exception.status_code, 404)
        with self.assertRaises(HTTPException) as invalid_format:
            self.ns['start_camera']('science', pixel_format='invalid')
        self.assertEqual(invalid_format.exception.status_code, 400)
        self.ns['start_camera']('video3', 640, 480, 24, 'MJPG')
        self.manager.start_camera.assert_called_once_with('video3', 640, 480, 24, 'MJPG')

    def test_generic_detected_cameras_are_accepted_by_webrtc(self):
        path = ROOT / 'app/api/navigation/camera_webrtc.py'
        tree = ast.parse(path.read_text())
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'webrtc_offer')
        node.decorator_list = []
        node.body = [n for n in node.body if not isinstance(n, ast.ImportFrom)]
        handle = Mock()
        async def offer(**kwargs):
            handle(**kwargs)
            return {'sdp': 'answer', 'type': 'answer', 'peer_id': 'one', 'adaptive_quality': True, 'target_fps': 24}
        ns = {'camera_manager': self.manager, 'CAMERA_DEVICES': {'science': 'device'},
              'WebRTCOfferRequest': object, 'HTTPException': HTTPException, 'handle_offer': offer}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), ns)
        self.manager.get_camera_status.return_value = {'active': True}
        result = asyncio.run(ns['webrtc_offer']('video3', SimpleNamespace(fps=24, sdp='offer', type='offer')))
        self.assertEqual(result['camera_name'], 'video3')
        self.assertEqual(handle.call_args.kwargs['source_name'], 'camera:video3')
        with self.assertRaises(HTTPException):
            asyncio.run(ns['webrtc_offer']('video-not-a-number', SimpleNamespace(fps=24)))


    def test_generic_websocket_cameras_reach_the_started_check(self):
        path = ROOT / 'app/api/navigation/camera_ws.py'
        tree = ast.parse(path.read_text())
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'camera_stream_ws')
        node.decorator_list = []
        node.body = [n for n in node.body if not isinstance(n, ast.ImportFrom)]
        class Socket:
            def __init__(self): self.messages = []
            async def accept(self): pass
            async def send_json(self, message): self.messages.append(message)
            async def close(self, **kwargs): pass
        ns = {'camera_manager': self.manager, 'CAMERA_DEVICES': {'science': 'device'},
              'WebSocket': object, 'Query': lambda default, **kwargs: default,
              'DEFAULT_QUALITY': 85, 'DEFAULT_FPS': 30}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), ns)
        self.manager.get_camera_status.return_value = {'active': False}
        socket = Socket()
        asyncio.run(ns['camera_stream_ws'](socket, 'video3'))
        self.assertIn('not started', socket.messages[0]['message'])
        self.manager.get_camera_status.assert_called_once_with('video3')

class CameraConcurrencyTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(SOURCE.read_text())
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MultiCameraManager')
        cv = SimpleNamespace(VideoCapture=object, CAP_PROP_FRAME_WIDTH=1, CAP_PROP_FRAME_HEIGHT=2, CAP_PROP_FPS=3)
        ns = {'cv2': cv, 'threading': threading, 'Optional': Optional}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), ns)
        self.manager = ns['MultiCameraManager']()

    def test_concurrent_starts_open_one_device(self):
        camera = Mock(); camera.isOpened.return_value = True
        self.manager._open_camera = Mock(return_value=camera)
        self.manager._device_path = lambda name: 'fake-device'
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertTrue(all(pool.map(lambda _: self.manager.start_camera('science'), range(8))))
        self.manager._open_camera.assert_called_once_with('science')

    def test_stop_waits_for_its_read_without_blocking_another_camera(self):
        reading = threading.Event(); finish = threading.Event()
        camera = Mock(); camera.isOpened.return_value = True
        def read():
            reading.set()
            if not finish.wait(2): raise RuntimeError('read was not released')
            return True, 'frame'
        camera.read.side_effect = read
        other = Mock(); other.isOpened.return_value = True; other.read.return_value = (True, 'other')
        self.manager.cameras.update(science=camera, rover=other)
        with ThreadPoolExecutor(max_workers=3) as pool:
            capture = pool.submit(self.manager.capture_frame, 'science')
            self.assertTrue(reading.wait(1))
            stopping = pool.submit(self.manager.stop_camera, 'science')
            self.assertEqual(pool.submit(self.manager.capture_frame, 'rover').result(timeout=1), 'other')
            self.assertFalse(camera.release.called)
            finish.set()
            self.assertEqual(capture.result(timeout=1), 'frame')
            self.assertTrue(stopping.result(timeout=1))
        self.assertIsNone(self.manager.capture_frame('science'))
        camera.release.assert_called_once()

if __name__ == '__main__':
    unittest.main()
