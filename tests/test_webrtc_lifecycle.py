"""Test actual registry/negotiation functions without aiortc or camera hardware.

AST loading avoids importing native media dependencies on this Windows host.
This tests peer ownership and cleanup, not ICE transport or FastAPI routing.
"""

import ast
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional
import unittest
from uuid import uuid4
from app.api.webrtc_signaling import defer_mdns_end_of_candidates


class FakePeer:
    def __init__(self, **kwargs):
        self.closed = False
        self.handlers = {}

    def on(self, name):
        def register(fn):
            self.handlers[name] = fn
            return fn
        return register

    def addTrack(self, track):
        pass

    async def setRemoteDescription(self, description):
        raise asyncio.CancelledError()

    async def close(self):
        self.closed = True


class WebRTCLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "app/api/webrtc_utils.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)]
        self.ns = {
            "asyncio": asyncio, "uuid4": uuid4, "Optional": Optional, "Callable": Callable,
            "RTCPeerConnection": FakePeer, "_peer_connections": {}, "_peer_ids": {}, "_peer_tracks": {},
            "_pc_lock": asyncio.Lock(), "MAX_WEBRTC_CLIENTS_PER_SOURCE": 5,
            "np": SimpleNamespace(ndarray=object), "ICE_CONFIG": None,
            "CameraVideoTrack": lambda **kwargs: object(),
            "RTCSessionDescription": lambda **kwargs: kwargs,
            "logger": logging.getLogger(__name__),
            "defer_mdns_end_of_candidates": defer_mdns_end_of_candidates,
        }
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), "exec"), self.ns)

    async def register(self, source="camera:science"):
        peer = FakePeer()
        self.assertTrue(await self.ns["register_peer_connection"](source, peer))
        return peer, self.ns["_peer_ids"][peer]

    async def test_closing_one_viewer_preserves_the_other(self):
        first, first_id = await self.register()
        second, second_id = await self.register()
        self.assertNotEqual(first_id, second_id)
        closed = await self.ns["close_peer_connection"]("camera:science", first_id)
        self.assertEqual(closed, 1)
        self.assertTrue(first.closed)
        self.assertFalse(second.closed)
        self.assertEqual(await self.ns["get_connection_count"]("camera:science"), 1)
        self.assertEqual(self.ns["_peer_ids"], {second: second_id})

    async def test_peer_id_cannot_close_another_source(self):
        peer, peer_id = await self.register()
        self.assertEqual(await self.ns["close_peer_connection"]("microscope", peer_id), 0)
        self.assertFalse(peer.closed)

    async def test_feedback_is_scoped_to_one_source_and_viewer(self):
        peer, peer_id = await self.register()
        other, _ = await self.register()
        received = []
        self.ns["_peer_tracks"][peer] = SimpleNamespace(feedback=lambda values: received.append(values) or {"scale": 0.85})
        self.ns["_peer_tracks"][other] = SimpleNamespace(feedback=lambda values: self.fail("Wrong viewer"))
        values = {"received_fps": 15}
        self.assertIsNone(await self.ns["update_peer_feedback"]("microscope", peer_id, values))
        self.assertEqual(await self.ns["update_peer_feedback"]("camera:science", peer_id, values), {"scale": 0.85})
        self.assertEqual(received, [values])
        await self.ns["close_peer_connection"]("camera:science", peer_id)
        self.assertNotIn(peer, self.ns["_peer_tracks"])
        self.assertIsNone(await self.ns["update_peer_feedback"]("camera:science", peer_id, values))

    async def test_repeated_close_is_idempotent(self):
        peer, peer_id = await self.register()
        self.assertEqual(await self.ns["close_peer_connection"]("camera:science", peer_id), 1)
        self.assertEqual(await self.ns["close_peer_connection"]("camera:science", peer_id), 0)
        self.assertEqual(self.ns["_peer_connections"], {})
        self.assertEqual(self.ns["_peer_ids"], {})

    async def test_legacy_close_all_remains_available_and_cleans_ids(self):
        first, _ = await self.register()
        second, _ = await self.register()
        other, other_id = await self.register("microscope")
        self.assertEqual(await self.ns["close_all_connections"]("camera:science"), 2)
        self.assertTrue(first.closed and second.closed)
        self.assertFalse(other.closed)
        self.assertEqual(self.ns["_peer_ids"], {other: other_id})

    async def test_capacity_rejection_does_not_evict_existing_viewers(self):
        for _ in range(5):
            await self.register()
        rejected = FakePeer()
        self.assertFalse(await self.ns["register_peer_connection"]("camera:science", rejected))
        self.assertNotIn(rejected, self.ns["_peer_ids"])
        self.assertEqual(await self.ns["get_connection_count"]("camera:science"), 5)

    async def test_cancelled_offer_releases_its_registration(self):
        with self.assertRaises(asyncio.CancelledError):
            await self.ns["handle_offer"]("camera:science", "offer", "offer", lambda: None)
        self.assertEqual(self.ns["_peer_connections"], {})
        self.assertEqual(self.ns["_peer_ids"], {})

    async def test_unregister_cleans_id_after_transport_failure(self):
        peer, _ = await self.register()
        await self.ns["unregister_peer_connection"]("camera:science", peer)
        self.assertEqual(self.ns["_peer_connections"], {})
        self.assertEqual(self.ns["_peer_ids"], {})

    async def test_successful_answer_returns_the_registered_peer_id(self):
        class SuccessfulPeer(FakePeer):
            iceGatheringState = "complete"

            async def setRemoteDescription(self, description):
                pass

            async def createAnswer(self):
                return SimpleNamespace(type="answer", sdp="a=candidate:fake")

            async def setLocalDescription(self, description):
                self.localDescription = description

        self.ns["RTCPeerConnection"] = SuccessfulPeer
        answer = await self.ns["handle_offer"]("camera:science", "offer", "offer", lambda: None)
        self.assertEqual(answer["type"], "answer")
        self.assertIn(answer["peer_id"], self.ns["_peer_ids"].values())
        self.assertEqual(await self.ns["close_peer_connection"]("camera:science", answer["peer_id"]), 1)

    async def test_zero_candidate_answer_fails_and_releases_slot(self):
        class EmptyPeer(FakePeer):
            iceGatheringState = "complete"
            async def setRemoteDescription(self, description):
                self.offer = description
            async def createAnswer(self):
                return SimpleNamespace(type="answer", sdp="v=0\r\n")
            async def setLocalDescription(self, description):
                self.localDescription = description
        self.ns["RTCPeerConnection"] = EmptyPeer
        with self.assertRaisesRegex(RuntimeError, "local ICE address"):
            await self.ns["handle_offer"]("camera:science", "offer", "offer", lambda: None)
        self.assertEqual(self.ns["_peer_connections"], {})
        self.assertEqual(self.ns["_peer_ids"], {})

    async def test_abandoned_offer_deadline_releases_slot(self):
        expired = asyncio.Event()
        class WaitingPeer(FakePeer):
            connectionState = "new"
            iceGatheringState = "complete"
            async def setRemoteDescription(self, description):
                pass
            async def createAnswer(self):
                return SimpleNamespace(type="answer", sdp="a=candidate:fake")
            async def setLocalDescription(self, description):
                self.localDescription = description
            async def close(self):
                self.closed = True
                expired.set()
        async def deadline_sleep(seconds):
            self.assertEqual(seconds, 30)
        self.ns["asyncio"] = SimpleNamespace(**{name: getattr(asyncio, name) for name in ("create_task", "current_task", "CancelledError")}, sleep=deadline_sleep)
        self.ns["RTCPeerConnection"] = WaitingPeer
        await self.ns["handle_offer"]("camera:science", "offer", "offer", lambda: None)
        await asyncio.wait_for(expired.wait(), timeout=1)
        self.assertEqual(self.ns["_peer_connections"], {})


if __name__ == "__main__":
    unittest.main()
