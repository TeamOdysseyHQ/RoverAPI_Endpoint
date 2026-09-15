"""Real ICE + RTP test; requires the rover's aiortc/av dependencies, no camera.

Run: python -m unittest discover -s tests -p test_webrtc_ice_integration.py
"""
import asyncio
import re
import unittest
from unittest.mock import patch

try:
    import numpy as np
    from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
    from app.api import webrtc_utils as rtc
except ImportError:
    rtc = None


@unittest.skipIf(rtc is None, "aiortc/av not installed")
class IceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_unresolvable_mdns_offer_connects_and_delivers_frames(self):
        client = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        source = "test:mdns-integration"
        track_ready = asyncio.get_running_loop().create_future()
        @client.on("track")
        def on_track(track):
            track_ready.set_result(track)
        try:
            client.addTransceiver("video", direction="recvonly")
            await client.setLocalDescription(await client.createOffer())
            offer = re.sub(r"(a=candidate:[^\r\n]+? udp \d+ )[^ ]+", r"\g<1>codex-unresolvable-probe.local", client.localDescription.sdp)
            self.assertIn(".local", offer)
            self.assertIn("a=end-of-candidates", offer)
            with patch.object(rtc, "ICE_CONFIG", RTCConfiguration(iceServers=[])):
                answer = await asyncio.wait_for(rtc.handle_offer(source, offer, "offer", lambda: np.zeros((240, 320, 3), dtype=np.uint8), fps=24), 10)
            self.assertIn("a=candidate:", answer["sdp"])
            await client.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
            track = await asyncio.wait_for(track_ready, 5)
            frames = [await asyncio.wait_for(track.recv(), 10) for _ in range(3)]
            self.assertEqual(client.connectionState, "connected")
            self.assertTrue(all(frame.width == 320 for frame in frames))
            self.assertGreater(frames[-1].pts, frames[0].pts)
            self.assertEqual(answer["target_fps"], 24)
            self.assertEqual(await rtc.close_peer_connection(source, answer["peer_id"]), 1)
            self.assertEqual(await rtc.get_connection_count(source), 0)
        finally:
            await client.close()
            await rtc.close_all_connections(source)


if __name__ == "__main__":
    unittest.main()
