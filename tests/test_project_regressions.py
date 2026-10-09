import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
import numpy as np
from fastapi import FastAPI, HTTPException, WebSocketDisconnect
from fastapi.testclient import TestClient

from app.api.navigation import camera, camera_ws, report as nav_report, report_handler as nav_handler, ros_camera, ros_camera_webrtc
from app.api.science import microscope, microscope_ws, report as sci_report, report_handler as sci_handler, sensor_data
from app.api.diagnostics import doctor
from app.api import ros_endpoints
from app.api.ros_image import decode_ros_image
from app.utils import expeditions


def application():
    app = FastAPI()
    app.include_router(camera.router, prefix="/nav")
    app.include_router(camera_ws.router, prefix="/nav")
    app.include_router(nav_report.router, prefix="/nav")
    app.include_router(sci_report.router, prefix="/sci")
    app.include_router(microscope.router, prefix="/sci")
    app.include_router(microscope_ws.router, prefix="/sci")
    app.include_router(ros_endpoints.router)
    return app


class StorageRouteTests(unittest.TestCase):
    def test_waypoint_routes_keep_concurrent_ids_and_names_unique(self):
        with TemporaryDirectory() as directory, patch.object(camera, "WAYPOINT_FILE", str(Path(directory) / "waypoints.json")):
            client = TestClient(application())
            with ThreadPoolExecutor(max_workers=6) as pool:
                responses = list(pool.map(lambda _: client.post("/nav/waypoint", data={"mission_id": "test"}), range(20)))
            entries = [response.json()["waypoint"] for response in responses]
            self.assertEqual(len({entry["waypoint_id"] for entry in entries}), 20)
            self.assertEqual(len({entry["name"] for entry in entries}), 20)
            self.assertEqual(client.get("/nav/get_waypoints").json()["count"], 20)

    def test_capture_uploads_preserve_bytes_and_metadata(self):
        with TemporaryDirectory() as directory, patch.object(camera, "IMAGE_DIR", directory), patch.object(camera, "META_FILE", str(Path(directory) / "metadata.json")):
            client = TestClient(application())
            responses = [client.post("/nav/capture", files={"image": ("rover.jpg", b"image-bytes", "image/jpeg")}) for _ in range(2)]
            names = [response.json()["saved"] for response in responses]
            self.assertEqual(len(set(names)), 2)
            self.assertTrue(all((Path(directory) / name).read_bytes() == b"image-bytes" for name in names))
            self.assertEqual(client.get("/nav/get_metadata").json()["count"], 2)

    def test_invalid_stream_and_camera_parameters_are_rejected(self):
        client = TestClient(application())
        self.assertEqual(client.post("/nav/cameras/rover/start", data={"fps": 0}).status_code, 422)
        self.assertEqual(client.post("/sci/microscope/start", data={"width": 0}).status_code, 422)
        with self.assertRaises(WebSocketDisconnect) as caught:
            with client.websocket_connect("/sci/microscope/stream/ws?fps=0"):
                pass
        self.assertEqual(caught.exception.code, 1008)

    def test_static_report_path_route_and_containment(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "reports"
            output.mkdir()
            allowed = output / "one.pdf"
            allowed.write_bytes(b"%PDF-allowed")
            outside = Path(directory) / "outside.pdf"
            outside.write_bytes(b"outside")
            with patch.object(sci_report, "REPORT_OUTPUT_DIR", str(output)), patch.object(sci_report, "REPORT_SOURCE_DIR", str(output)):
                client = TestClient(application())
                response = client.get("/sci/report/by_path", params={"path": str(allowed)})
                self.assertEqual(response.content, b"%PDF-allowed")
                self.assertFalse(client.get("/sci/report/by_path", params={"path": str(outside)}).json()["success"])
                self.assertEqual(sci_report.verify_report_access("../outside", None), 0)


class ExpeditionTests(unittest.TestCase):
    def test_captures_and_both_report_routes_share_expeditions(self):
        with TemporaryDirectory() as directory, patch.object(expeditions, "EXPEDITION_BASE_DIR", str(Path(directory) / "unprocessed")), patch.object(expeditions, "EXPEDITION_PROCESSED_DIR", str(Path(directory) / "processed")):
            client = TestClient(application())
            for prefix in ("/sci", "/nav"):
                expedition_id = client.post(prefix + "/assign_expedition").json()["expedition_id"]
                capture_path = camera.get_safe_expedition_dir(expedition_id)
                self.assertEqual(capture_path, microscope.get_safe_expedition_dir(expedition_id))
                for check_prefix in ("/sci", "/nav"):
                    self.assertEqual(client.get(check_prefix + "/expedition_check/" + expedition_id).json()["expedition_status"], "unprocessed")
            for invalid in ("", ".", "..", "../escape", "a/b", "a\\b"):
                with self.assertRaises(HTTPException):
                    expeditions.expedition_path(invalid)

    def test_report_filename_parser_supports_old_and_new_captures(self):
        for filename in ("20261009_120000_rover_capture.jpg", "20261009_120000_123456_rover_capture.jpg", "1720000000_123_rover_capture.jpg"):
            camera_name, stamp = expeditions.capture_details(filename)
            self.assertEqual(camera_name, "rover")
            self.assertNotEqual(stamp, "Unknown")
        self.assertEqual(expeditions.capture_details("uploaded.jpg"), ("unknown", "Unknown"))

    def test_failed_compilation_does_not_mark_expedition_processed(self):
        for module, handler_type in ((nav_handler, nav_handler.NavigationReportHandler), (sci_handler, sci_handler.ReportHandler)):
            with self.subTest(module=module.__name__), TemporaryDirectory() as directory:
                root = Path(directory)
                with patch.object(expeditions, "EXPEDITION_BASE_DIR", str(root / "unprocessed")), patch.object(expeditions, "EXPEDITION_PROCESSED_DIR", str(root / "processed")), patch.object(module, "REPORT_SOURCE_DIR", str(root)), patch.object(module, "REPORT_OUTPUT_DIR", str(root)), patch.object(module.ros_manager, "is_connected", False):
                    expedition_id = expeditions.create_expedition()
                    (Path(expeditions.expedition_path(expedition_id)) / "20261009_120000_123456_rover_capture.jpg").write_bytes(b"image")
                    handler = handler_type(expedition_id=expedition_id)
                    with patch.object(handler, "_generate_typst_report"), patch.object(module.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "typst", stderr="failed")):
                        with self.assertRaises(module.ReportGenerationFailure):
                            handler.create_report(force_gen=True)
                    self.assertFalse(Path(expeditions.expedition_path(expedition_id, processed=True)).exists())

    def test_successful_reports_include_microsecond_captures_and_then_mark_processed(self):
        for module, handler_type, metadata in ((nav_handler, nav_handler.NavigationReportHandler, "nav_metadata.dat"), (sci_handler, sci_handler.ReportHandler, "metadata.dat")):
            with self.subTest(module=module.__name__), TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "source"
                output = root / "output"
                source.mkdir()
                output.mkdir()
                with patch.object(expeditions, "EXPEDITION_BASE_DIR", str(root / "unprocessed")), patch.object(expeditions, "EXPEDITION_PROCESSED_DIR", str(root / "processed")), patch.object(module, "REPORT_SOURCE_DIR", str(source)), patch.object(module, "REPORT_OUTPUT_DIR", str(output)), patch.object(module.ros_manager, "is_connected", False):
                    expedition_id = expeditions.create_expedition()
                    filename = "20261009_120000_123456_rover_capture.jpg"
                    (Path(expeditions.expedition_path(expedition_id)) / filename).write_bytes(b"image")
                    handler = handler_type(expedition_id=expedition_id)
                    def compile_report(*args, **kwargs):
                        Path(handler.fileloc_compiled).write_bytes(b"%PDF-test")
                        return SimpleNamespace(returncode=0)
                    with patch.object(handler, "_generate_typst_report") as generate, patch.object(module.subprocess, "run", side_effect=compile_report):
                        report_id, _ = handler.create_report(force_gen=True)
                    images = generate.call_args.args[1]
                    entry = images[filename] if module is nav_handler else images["rover"][filename]
                    if module is nav_handler:
                        self.assertEqual(entry["camera"], "rover")
                        self.assertEqual(entry["timestamp"], "2026-10-09 12:00:00")
                    self.assertEqual((output / (report_id + ".pdf")).read_bytes(), b"%PDF-test")
                    processed = Path(expeditions.expedition_path(expedition_id, processed=True))
                    self.assertEqual((processed / metadata).read_text().strip(), report_id)
                    self.assertEqual((processed / filename).read_bytes(), b"image")


class RosImageTests(unittest.TestCase):
    def test_padded_rgb_bgr_and_mono_rows(self):
        for encoding, channels in (("rgb8", 3), ("bgr8", 3), ("mono8", 1)):
            with self.subTest(encoding=encoding):
                row = bytes(range(1, channels * 2 + 1))
                payload = (row + b"\xff\xff") * 2
                message = {"width": 2, "height": 2, "encoding": encoding, "step": len(row) + 2, "data": base64.b64encode(payload).decode()}
                frame = decode_ros_image(message)
                self.assertEqual(frame.shape, (2, 2, 3))
                expected = [3, 2, 1] if encoding == "rgb8" else ([1, 2, 3] if encoding == "bgr8" else [1, 1, 1])
                self.assertEqual(frame[0, 0].tolist(), expected)
                self.assertEqual(frame[1, 0].tolist(), expected)
                message["data"] = list(payload)
                self.assertTrue(np.array_equal(frame, decode_ros_image(message)))

    def test_truncated_or_unsupported_images_are_rejected(self):
        message = {"width": 2, "height": 2, "encoding": "bgr8", "step": 6, "data": "AA=="}
        self.assertIsNone(decode_ros_image(message))
        self.assertIsNone(decode_ros_image({**message, "step": 1}))
        self.assertIsNone(decode_ros_image({**message, "encoding": "16UC1"}))


class SensorAndDiagnosticTests(unittest.TestCase):
    def test_cached_sensor_data_returns_without_sleep(self):
        manager = Mock(is_connected=True)
        manager._subscribers = {sensor_data.SCIENCE_DATA_TOPIC: object()}
        manager.get_latest_message.return_value = {"data": list(range(14))}
        with patch.object(sensor_data, "ros_manager", manager), patch.object(sensor_data.time, "sleep") as sleep:
            self.assertTrue(sensor_data.sci_sensor_data()["success"])
            sleep.assert_not_called()
            manager.get_latest_message.return_value = {"data": [1]}
            self.assertFalse(sensor_data.sci_sensor_data()["success"])

    def test_doctor_reports_multiline_failures_warnings_and_success(self):
        for output, code, expected in (("Header\n2/4 checks failed", 0, "Errors"), ("Header\nUserWarning: x", 0, "Success with warnings"), ("All checks passed", 0, "Success"), ("0/4 checks failed", 0, "Success"), ("failed", 1, "Errors")):
            with self.subTest(output=output), patch.object(doctor.subprocess, "run", return_value=SimpleNamespace(stdout=output, stderr="", returncode=code)):
                self.assertEqual(doctor.ros2_doctor()["status"], expected)


class ResponsivenessTests(unittest.IsolatedAsyncioTestCase):
    async def test_ros_mjpeg_waits_for_a_new_message_instead_of_resending(self):
        manager = Mock(is_connected=True)
        first_message = {"frame": 1}
        manager.get_latest_camera_image.return_value = first_message
        with patch.object(ros_camera, "ros_manager", manager), patch.object(ros_camera, "encode_ros_jpeg", return_value=b"jpeg") as encode:
            response = await ros_camera.stream_camera_mjpeg(None, 30, 85)
            stream = response.body_iterator
            self.assertIn(b"jpeg", await anext(stream))
            waiting = asyncio.create_task(anext(stream))
            try:
                await asyncio.sleep(0.08)
                self.assertFalse(waiting.done())
                self.assertEqual(encode.call_count, 1)
                manager.get_latest_camera_image.return_value = {"frame": 2}
                self.assertIn(b"jpeg", await asyncio.wait_for(waiting, 1))
                self.assertEqual(encode.call_count, 2)
            finally:
                if not waiting.done():
                    waiting.cancel()
                    try:
                        await waiting
                    except asyncio.CancelledError:
                        pass
                await stream.aclose()

    async def test_ros_webrtc_reuses_decoding_until_message_changes(self):
        manager = Mock()
        manager.get_latest_camera_image.return_value = {"frame": 1}
        frame = np.zeros((2, 2, 3), dtype=np.uint8)
        with patch.object(ros_camera_webrtc, "ros_manager", manager), patch.object(ros_camera_webrtc, "decode_ros_image", return_value=frame) as decode:
            capture = ros_camera_webrtc._make_ros_capture("/camera")
            self.assertIs(capture(), frame)
            self.assertIs(capture(), frame)
            self.assertEqual(decode.call_count, 1)
            manager.get_latest_camera_image.return_value = {"frame": 2}
            self.assertIs(capture(), frame)
            self.assertEqual(decode.call_count, 2)

    async def test_jpeg_encoding_runs_off_the_event_loop_and_releases_clients(self):
        entered = threading.Event()
        release = threading.Event()
        encoder_threads = []
        def encode(*args):
            encoder_threads.append(threading.get_ident())
            entered.set()
            if not release.wait(3):
                raise RuntimeError("test did not release encoder")
            return b"frame"
        manager = Mock()
        manager.get_camera_status.return_value = {"active": True, "width": 640, "height": 480}
        socket = SimpleNamespace(accept=AsyncMock(), close=AsyncMock(), send_json=AsyncMock(), send_bytes=AsyncMock(side_effect=RuntimeError("viewer left")))
        async def receive():
            await asyncio.Future()
        socket.receive_text = receive
        connections = camera_ws.WebSocketConnectionManager()
        with patch.object(camera, "camera_manager", manager), patch.object(camera_ws, "ws_manager", connections), patch.object(camera_ws, "_capture_encoded_frame", side_effect=encode):
            streaming = asyncio.create_task(camera_ws.camera_stream_ws(socket, "rover", 85, 30))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                self.assertNotEqual(encoder_threads[0], threading.get_ident())
                await asyncio.wait_for(asyncio.sleep(0), timeout=0.5)
            finally:
                release.set()
                await streaming
            self.assertEqual(connections.get_connection_count("rover"), 0)
            manager.remove_ws_client.assert_called_once_with("rover", socket)

    async def test_cancelled_initial_status_send_releases_client(self):
        manager = Mock()
        manager.get_camera_status.return_value = {"active": True, "width": 640, "height": 480}
        socket = SimpleNamespace(accept=AsyncMock(), close=AsyncMock(), send_json=AsyncMock(side_effect=asyncio.CancelledError()))
        connections = camera_ws.WebSocketConnectionManager()
        with patch.object(camera, "camera_manager", manager), patch.object(camera_ws, "ws_manager", connections):
            with self.assertRaises(asyncio.CancelledError):
                await camera_ws.camera_stream_ws(socket, "rover", 85, 30)
            self.assertEqual(connections.get_connection_count("rover"), 0)
            manager.remove_ws_client.assert_called_once()

    async def test_microscope_initial_status_failure_releases_client(self):
        manager = Mock()
        manager.get_status.return_value = {"active": True, "width": 640, "height": 480}
        manager.add_ws_client.return_value = True
        socket = SimpleNamespace(accept=AsyncMock(), close=AsyncMock(), send_json=AsyncMock(side_effect=RuntimeError("viewer left")))
        with patch.object(microscope_ws, "microscope_manager", manager):
            with self.assertRaises(RuntimeError):
                await microscope_ws.microscope_websocket_stream(socket, 85, 30)
            manager.remove_ws_client.assert_called_once_with(socket)

    async def test_slow_ros_connect_does_not_block_health_request(self):
        app = application()
        entered = threading.Event()
        release = threading.Event()
        def connect():
            entered.set()
            if not release.wait(3):
                raise RuntimeError("test did not release connect")
            return True
        with patch.object(ros_endpoints.ros_manager, "is_connected", False), patch.object(ros_endpoints.ros_manager, "connect", side_effect=connect):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                connecting = asyncio.create_task(client.post("/ros/connect"))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                    response = await asyncio.wait_for(client.get("/status"), timeout=0.5)
                    self.assertEqual(response.status_code, 200)
                    self.assertFalse(connecting.done())
                finally:
                    release.set()
                    await connecting

    async def test_websocket_capacity_is_enforced_atomically(self):
        manager = camera_ws.WebSocketConnectionManager()
        sockets = [Mock() for _ in range(20)]
        outcomes = await asyncio.gather(*(manager.connect("rover", socket, accepted=True) for socket in sockets))
        self.assertEqual(sum(outcomes), camera_ws.MAX_CLIENTS_PER_CAMERA)
        for socket, accepted in zip(sockets, outcomes):
            if accepted:
                await manager.disconnect("rover", socket)
        self.assertEqual(manager.get_connection_count("rover"), 0)


if __name__ == "__main__":
    unittest.main()
