"""
Shared WebRTC utilities for camera streaming via aiortc.

Provides a reusable video track that wraps any frame-capture callable,
peer connection lifecycle management, and SDP offer/answer handling.
"""

import asyncio
import logging
import time
from fractions import Fraction
from typing import Callable, Dict, List, Optional
from uuid import uuid4

import av
import numpy as np
from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
)
from aiortc.contrib.media import MediaRelay
from aiortc.mediastreams import VideoStreamTrack
from app.api.stream_adaptation import AdaptiveQuality, FramePacer
from app.api.webrtc_signaling import defer_mdns_end_of_candidates
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Global media relay for efficient multi-client streaming
relay = MediaRelay()

# ICE server configuration – STUN for NAT traversal on LAN / remote
ICE_CONFIG = RTCConfiguration(
    iceServers=[
        RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
        RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
    ]
)

# Track active peer connections for cleanup
_peer_connections: Dict[str, List[RTCPeerConnection]] = {}
_peer_ids: Dict[RTCPeerConnection, str] = {}
_peer_tracks: Dict[RTCPeerConnection, "CameraVideoTrack"] = {}
_pc_lock = asyncio.Lock()

MAX_WEBRTC_CLIENTS_PER_SOURCE = 5


class VideoFeedback(BaseModel):
    received_fps: float = Field(ge=0, le=240, allow_inf_nan=False)
    loss_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)
    jitter_ms: float = Field(ge=0, le=60000, allow_inf_nan=False)
    decode_ms: float = Field(ge=0, le=60000, allow_inf_nan=False)


class CameraVideoTrack(VideoStreamTrack):
    """
    A video track that reads frames from a capture callable and converts
    them to av.VideoFrame for WebRTC transmission.

    Uses a monotonic per-track clock for the requested FPS instead of
    VideoStreamTrack.next_timestamp(), which always paces at 30 FPS.

    The capture callable should return a numpy array (OpenCV BGR frame)
    or None if no frame is available.
    """

    kind = "video"

    def __init__(
        self,
        capture_fn: Callable[[], Optional[np.ndarray]],
        fps: int = 30,
        source_name: str = "camera",
    ):
        super().__init__()
        self._capture_fn = capture_fn
        self._fps = fps
        self._source_name = source_name
        self._frame_time = 1.0 / fps
        self._start_time = time.time()
        self._frame_count = 0
        self._null_frame_count = 0
        self.quality = AdaptiveQuality(fps)
        self._pacer = FramePacer(fps)
        self._last_feedback = None

    def feedback(self, values):
        now = time.monotonic()
        # Rate limit each viewer's adaptation independently.
        if self._last_feedback is None or now - self._last_feedback >= 1:
            self.quality.update(values)
            self._last_feedback = now
        return {"target_fps": self.quality.target_fps, "scale": self.quality.scale, "bitrate_control": "rtcp-remb"}

    async def recv(self) -> av.VideoFrame:
        """Receive the next video frame."""
        # Pace frame delivery to target FPS
        await asyncio.sleep(self._pacer.delay(time.monotonic()))
        pts, time_base = self._pacer.timestamp(time.monotonic()), Fraction(1, 90000)

        loop = asyncio.get_running_loop()

        # Run the blocking capture in an executor
        try:
            frame = await loop.run_in_executor(None, self._capture_fn)
        except Exception as exc:
            logger.error(
                "[WebRTC:%s] capture_fn raised: %s", self._source_name, exc
            )
            frame = None

        if frame is None:
            self._null_frame_count += 1
            if self._null_frame_count <= 5 or self._null_frame_count % 100 == 0:
                logger.warning(
                    "[WebRTC:%s] capture_fn returned None "
                    "(null_count=%d, total_frames=%d)",
                    self._source_name,
                    self._null_frame_count,
                    self._frame_count,
                )
            black = np.zeros((480, 640, 3), dtype=np.uint8)
            video_frame = av.VideoFrame.from_ndarray(black, format="bgr24")
        else:
            if self._null_frame_count > 0:
                logger.info(
                    "[WebRTC:%s] Frame capture recovered after %d null frames",
                    self._source_name,
                    self._null_frame_count,
                )
                self._null_frame_count = 0
            video_frame = av.VideoFrame.from_ndarray(frame, format="bgr24")

        if self.quality.scale < 1:
            # Scale only this viewer's encoded frames, not the physical camera.
            # Keep even dimensions for chroma subsampling, never upscale.
            scale = max(self.quality.scale, min(1, max(320 / video_frame.width, 240 / video_frame.height)))
            width = max(2, int(video_frame.width * scale) // 2 * 2)
            height = max(2, int(video_frame.height * scale) // 2 * 2)
            video_frame = video_frame.reformat(width=width, height=height)
        video_frame.pts = pts
        video_frame.time_base = time_base
        self._frame_count += 1

        if self._frame_count == 1:
            logger.info(
                "[WebRTC:%s] First frame produced (shape=%s)",
                self._source_name,
                frame.shape if frame is not None else "None",
            )

        return video_frame


async def get_connection_count(source_name: str) -> int:
    """Get number of active WebRTC connections for a source."""
    async with _pc_lock:
        return len(_peer_connections.get(source_name, []))


async def register_peer_connection(
    source_name: str, pc: RTCPeerConnection
) -> bool:
    """Register a peer connection. Returns False if limit exceeded."""
    async with _pc_lock:
        conns = _peer_connections.setdefault(source_name, [])
        if len(conns) >= MAX_WEBRTC_CLIENTS_PER_SOURCE:
            return False
        conns.append(pc)
        _peer_ids[pc] = uuid4().hex
    return True


async def unregister_peer_connection(
    source_name: str, pc: RTCPeerConnection
):
    """Remove a peer connection from tracking."""
    async with _pc_lock:
        _peer_ids.pop(pc, None)
        _peer_tracks.pop(pc, None)
        if source_name in _peer_connections:
            if pc in _peer_connections[source_name]:
                _peer_connections[source_name].remove(pc)
            if not _peer_connections[source_name]:
                del _peer_connections[source_name]


async def handle_offer(
    source_name: str,
    sdp: str,
    sdp_type: str,
    capture_fn: Callable[[], Optional[np.ndarray]],
    fps: int = 30,
) -> dict:
    """
    Process an SDP offer and return an SDP answer.

    Creates a new RTCPeerConnection, adds the video track, and
    completes the SDP exchange.

    Returns dict with 'sdp' and 'type' keys for the answer.
    Raises ValueError if connection limit exceeded or SDP exchange fails.
    """
    # Check connection limit
    count = await get_connection_count(source_name)
    if count >= MAX_WEBRTC_CLIENTS_PER_SOURCE:
        raise ValueError(
            f"Too many WebRTC clients for '{source_name}' "
            f"(max {MAX_WEBRTC_CLIENTS_PER_SOURCE})"
        )

    pc = RTCPeerConnection(configuration=ICE_CONFIG)
    connection_deadline = None

    # ---------- diagnostics ----------
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(
            "[WebRTC:%s] Connection state -> %s",
            source_name,
            pc.connectionState,
        )
        if pc.connectionState in ("connected", "failed", "closed"):
            if connection_deadline and connection_deadline is not asyncio.current_task():
                connection_deadline.cancel()
        if pc.connectionState in ("failed", "closed"):
            await unregister_peer_connection(source_name, pc)
            await pc.close()

    @pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        logger.info(
            "[WebRTC:%s] ICE connection state -> %s",
            source_name,
            pc.iceConnectionState,
        )

    @pc.on("icegatheringstatechange")
    async def on_icegatheringstatechange():
        logger.info(
            "[WebRTC:%s] ICE gathering state -> %s",
            source_name,
            pc.iceGatheringState,
        )
    # ---------------------------------

    # Register the peer connection
    registered = await register_peer_connection(source_name, pc)
    if not registered:
        await pc.close()
        raise ValueError(
            f"Too many WebRTC clients for '{source_name}'"
        )

    async def expire_unconnected_peer():
        # A lost HTTP response or vanished browser must not reserve a viewer
        # slot forever, including when mDNS end-of-candidates is deferred.
        await asyncio.sleep(30)
        if pc.connectionState != "connected":
            logger.warning("[WebRTC:%s] Connection deadline expired", source_name)
            await unregister_peer_connection(source_name, pc)
            await pc.close()

    connection_deadline = asyncio.create_task(expire_unconnected_peer())

    # Create and add the video track, then complete SDP exchange.
    # Wrapped in try/except so the peer is always cleaned up on failure.
    try:
        video_track = CameraVideoTrack(
            capture_fn=capture_fn,
            fps=fps,
            source_name=source_name,
        )
        pc.addTrack(video_track)
        _peer_tracks[pc] = video_track

        # Set remote description (the offer)
        offer = RTCSessionDescription(sdp=defer_mdns_end_of_candidates(sdp), type=sdp_type)
        await pc.setRemoteDescription(offer)

        # Create and set local description (the answer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        # Ensure ICE candidates have been gathered before returning the SDP.
        # Without candidates in the answer the client cannot reach us.
        gather_timeout = 10  # seconds
        waited = 0.0
        while pc.iceGatheringState != "complete" and waited < gather_timeout:
            await asyncio.sleep(0.05)
            waited += 0.05

        sdp_text = pc.localDescription.sdp
        candidate_count = sdp_text.count("a=candidate:")
        logger.info(
            "[WebRTC:%s] SDP answer ready – %d ICE candidate(s), "
            "gathering state: %s",
            source_name,
            candidate_count,
            pc.iceGatheringState,
        )
        if candidate_count == 0:
            raise RuntimeError("WebRTC could not gather a local ICE address; check the rover network interfaces")

        return {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
            "peer_id": _peer_ids[pc],
            "adaptive_quality": True,
            "target_fps": fps,
        }
    except (Exception, asyncio.CancelledError):
        # SDP negotiation failed — clean up the registered peer so it
        # doesn't leak a connection slot.
        connection_deadline.cancel()
        await unregister_peer_connection(source_name, pc)
        await pc.close()
        raise


async def update_peer_feedback(source_name: str, peer_id: str, feedback: dict) -> Optional[dict]:
    async with _pc_lock:
        peer = next((pc for pc in _peer_connections.get(source_name, []) if _peer_ids.get(pc) == peer_id), None)
        track = _peer_tracks.get(peer)
        return track.feedback(feedback) if track else None


async def close_peer_connection(source_name: str, peer_id: str) -> int:
    """Close only the requesting viewer, never another source or viewer."""
    async with _pc_lock:
        conns = _peer_connections.get(source_name, [])
        pc = next((peer for peer in conns if _peer_ids.get(peer) == peer_id), None)
        if pc is None:
            return 0
        conns.remove(pc)
        _peer_ids.pop(pc, None)
        _peer_tracks.pop(pc, None)
        if not conns:
            _peer_connections.pop(source_name, None)
    await pc.close()
    return 1


async def close_all_connections(source_name: str) -> int:
    """Close all WebRTC connections for a source. Returns count closed."""
    async with _pc_lock:
        conns = _peer_connections.pop(source_name, [])
        for pc in conns:
            _peer_ids.pop(pc, None)
            _peer_tracks.pop(pc, None)

    closed = 0
    for pc in conns:
        try:
            await pc.close()
            closed += 1
        except Exception:
            pass
    return closed


async def get_all_webrtc_stats() -> dict:
    """Get WebRTC connection stats for all sources."""
    async with _pc_lock:
        return {
            source: {
                "active_connections": len(conns),
                "max_connections": MAX_WEBRTC_CLIENTS_PER_SOURCE,
            }
            for source, conns in _peer_connections.items()
        }
