"""
Shared WebRTC utilities for camera streaming via aiortc.

Provides a reusable video track that wraps any frame-capture callable,
peer connection lifecycle management, and SDP offer/answer handling.
"""

import asyncio
import logging
import time
from typing import Callable, Dict, List, Optional

import av
import cv2
import numpy as np
from aiortc import (
    MediaStreamTrack,
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
)
from aiortc.contrib.media import MediaRelay

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
_pc_lock = asyncio.Lock()

MAX_WEBRTC_CLIENTS_PER_SOURCE = 5


class CameraVideoTrack(MediaStreamTrack):
    """
    A video track that reads frames from a capture callable and converts
    them to av.VideoFrame for WebRTC transmission.

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

    async def recv(self) -> av.VideoFrame:
        """Receive the next video frame."""
        # Pace frame delivery to target FPS
        pts, time_base = await self.next_timestamp()

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
    return True


async def unregister_peer_connection(
    source_name: str, pc: RTCPeerConnection
):
    """Remove a peer connection from tracking."""
    async with _pc_lock:
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

    # ---------- diagnostics ----------
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(
            "[WebRTC:%s] Connection state -> %s",
            source_name,
            pc.connectionState,
        )
        if pc.connectionState in ("failed", "closed", "disconnected"):
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

    # Create and add the video track
    video_track = CameraVideoTrack(
        capture_fn=capture_fn,
        fps=fps,
        source_name=source_name,
    )
    pc.addTrack(video_track)

    # Set remote description (the offer)
    offer = RTCSessionDescription(sdp=sdp, type=sdp_type)
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
        logger.warning(
            "[WebRTC:%s] No ICE candidates in SDP answer! "
            "The client will likely fail to connect.",
            source_name,
        )

    return {
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
    }


async def close_all_connections(source_name: str) -> int:
    """Close all WebRTC connections for a source. Returns count closed."""
    async with _pc_lock:
        conns = _peer_connections.pop(source_name, [])

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
