#!/usr/bin/env python3
"""
Test script for WebSocket camera streaming.

This script connects to the WebSocket camera stream endpoint and
validates the binary frame protocol.

Usage:
    python test_ws_camera_stream.py [camera_index] [duration_seconds]

Example:
    python test_ws_camera_stream.py 0 10

Prerequisites:
    1. Start the backend server: uv run main.py
    2. Start a camera: curl -X POST http://localhost:6767/api/nav/cameras/0/start
    3. Run this test script
"""

import asyncio
import struct
import time
import sys
from pathlib import Path

try:
    import websockets
except ImportError:
    print("Error: websockets library not found")
    print("Install with: pip install websockets")
    sys.exit(1)


# Protocol constants (must match camera_ws.py)
MAGIC_NUMBER = 0x524F5652  # "ROVR" in ASCII
HEADER_SIZE = 24


class WebSocketCameraTest:
    """Test client for WebSocket camera streaming"""

    def __init__(self, camera_index: int = 0, quality: int = 85, fps: int = 30):
        self.camera_index = camera_index
        self.quality = quality
        self.fps = fps
        self.uri = f"ws://localhost:6767/api/nav/cameras/{camera_index}/ws?quality={quality}&fps={fps}"

        # Statistics
        self.frames_received = 0
        self.bytes_received = 0
        self.errors = 0
        self.start_time = None
        self.first_frame_time = None
        self.last_frame_time = None

        # Latency tracking
        self.latencies = []

    async def connect_and_stream(self, duration: int = 10):
        """
        Connect to WebSocket and receive frames for specified duration.

        Args:
            duration: Test duration in seconds
        """
        print(f"Connecting to {self.uri}")
        print(f"Test duration: {duration} seconds")
        print("-" * 60)

        try:
            async with websockets.connect(self.uri) as websocket:
                print("✓ Connected successfully")
                self.start_time = time.time()

                # Receive initial status message (JSON)
                try:
                    status_msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)

                    if isinstance(status_msg, str):
                        import json

                        status = json.loads(status_msg)
                        print(f"✓ Received status: {status}")
                        print("-" * 60)
                    else:
                        print("Warning: First message was not status JSON")
                except asyncio.TimeoutError:
                    print("Warning: No initial status received")

                # Receive frames for specified duration
                end_time = time.time() + duration

                while time.time() < end_time:
                    try:
                        # Receive frame with timeout
                        message = await asyncio.wait_for(websocket.recv(), timeout=1.0)

                        if isinstance(message, bytes):
                            self.process_frame(message)
                        else:
                            print(f"Warning: Received text message: {message}")

                    except asyncio.TimeoutError:
                        print("Warning: Frame timeout (1 second)")
                        self.errors += 1
                    except Exception as e:
                        print(f"Error receiving frame: {e}")
                        self.errors += 1
                        break

                # Send test control message
                await self.send_control_message(websocket, "ping")

                # Wait for pong
                try:
                    pong = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    if isinstance(pong, str):
                        import json

                        pong_data = json.loads(pong)
                        if pong_data.get("type") == "pong":
                            print("\n✓ Ping/pong test successful")
                except:
                    pass

        except ConnectionRefusedError:
            print("✗ Connection refused. Is the server running?")
            print("  Start server with: cd endpoint && uv run main.py")
            return

        except Exception as e:
            error_str = str(e)

            # Check for WebSocket close codes
            if "4000" in error_str:
                print(f"✗ Camera {self.camera_index} is not started")
                print(
                    f"  Start it with: curl -X POST http://localhost:6767/api/nav/cameras/{self.camera_index}/start"
                )
            elif "4001" in error_str:
                print(f"✗ Too many clients connected to camera {self.camera_index}")
            else:
                print(f"✗ Error: {e}")
            return

        # Print statistics
        self.print_statistics()

    def process_frame(self, message: bytes):
        """Process received binary frame"""
        if len(message) < HEADER_SIZE:
            print(f"Warning: Message too short ({len(message)} bytes)")
            self.errors += 1
            return

        # Parse header
        try:
            header_data = struct.unpack("<IiQIBxxx", message[:HEADER_SIZE])
            magic, cam_idx, timestamp_us, frame_num, quality = header_data

            # Validate magic number
            if magic != MAGIC_NUMBER:
                print(f"Warning: Invalid magic number: {hex(magic)}")
                self.errors += 1
                return

            # Validate camera index
            if cam_idx != self.camera_index:
                print(
                    f"Warning: Wrong camera index: {cam_idx} (expected {self.camera_index})"
                )
                self.errors += 1
                return

            # Extract JPEG data
            jpeg_data = message[HEADER_SIZE:]
            jpeg_size = len(jpeg_data)

            # Calculate latency
            now_us = int(time.time() * 1_000_000)
            latency_ms = (now_us - timestamp_us) / 1000.0
            self.latencies.append(latency_ms)

            # Update statistics
            self.frames_received += 1
            self.bytes_received += len(message)

            if self.first_frame_time is None:
                self.first_frame_time = time.time()
            self.last_frame_time = time.time()

            # Print progress every 30 frames
            if self.frames_received % 30 == 0:
                if self.start_time is not None:
                    elapsed = time.time() - self.start_time
                    actual_fps = self.frames_received / elapsed if elapsed > 0 else 0
                    avg_latency = sum(self.latencies[-30:]) / min(
                        30, len(self.latencies)
                    )

                    print(
                        f"Frame {frame_num:4d} | "
                        f"Size: {jpeg_size:6d}B | "
                        f"Quality: {quality:3d} | "
                        f"Latency: {latency_ms:6.1f}ms | "
                        f"FPS: {actual_fps:5.1f}"
                    )

        except struct.error as e:
            print(f"Warning: Header parsing error: {e}")
            self.errors += 1
        except Exception as e:
            print(f"Warning: Frame processing error: {e}")
            self.errors += 1

    async def send_control_message(self, websocket, msg_type: str):
        """Send control message to server"""
        import json

        message = {"type": msg_type}
        await websocket.send(json.dumps(message))
        print(f"\nSent control message: {msg_type}")

    def print_statistics(self):
        """Print test statistics"""
        print("\n" + "=" * 60)
        print("TEST RESULTS")
        print("=" * 60)

        if self.start_time is None:
            print("No statistics available (connection failed)")
            return

        elapsed = time.time() - self.start_time

        print(f"Duration:          {elapsed:.2f} seconds")
        print(f"Frames received:   {self.frames_received}")
        print(
            f"Bytes received:    {self.bytes_received:,} ({self.bytes_received / 1024 / 1024:.2f} MB)"
        )
        print(f"Errors:            {self.errors}")

        if self.frames_received > 0:
            actual_fps = self.frames_received / elapsed
            avg_frame_size = self.bytes_received / self.frames_received
            avg_latency = sum(self.latencies) / len(self.latencies)
            min_latency = min(self.latencies)
            max_latency = max(self.latencies)

            print(f"\nPerformance:")
            print(f"  Actual FPS:      {actual_fps:.2f} (target: {self.fps})")
            print(f"  Avg frame size:  {avg_frame_size:,.0f} bytes")
            print(f"  Bandwidth:       {self.bytes_received / elapsed / 1024:.1f} KB/s")

            print(f"\nLatency:")
            print(f"  Average:         {avg_latency:.1f} ms")
            print(f"  Min:             {min_latency:.1f} ms")
            print(f"  Max:             {max_latency:.1f} ms")

            # Evaluation
            print(f"\nEvaluation:")
            fps_diff = abs(actual_fps - self.fps)
            if fps_diff < 2:
                print(f"  ✓ FPS: Excellent (within {fps_diff:.1f} of target)")
            elif fps_diff < 5:
                print(f"  ⚠ FPS: Good (within {fps_diff:.1f} of target)")
            else:
                print(f"  ✗ FPS: Poor (off by {fps_diff:.1f})")

            if avg_latency < 200:
                print(f"  ✓ Latency: Excellent (<200ms)")
            elif avg_latency < 500:
                print(f"  ⚠ Latency: Good (<500ms)")
            else:
                print(f"  ✗ Latency: Poor (>500ms)")

            if self.errors == 0:
                print(f"  ✓ Reliability: Perfect (no errors)")
            elif self.errors < self.frames_received * 0.01:
                print(f"  ⚠ Reliability: Good (<1% error rate)")
            else:
                print(
                    f"  ✗ Reliability: Poor ({self.errors / self.frames_received * 100:.1f}% error rate)"
                )

        print("=" * 60)


async def main():
    """Main entry point"""
    # Parse command line arguments
    camera_index = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    quality = int(sys.argv[3]) if len(sys.argv) > 3 else 85
    fps = int(sys.argv[4]) if len(sys.argv) > 4 else 30

    # Create and run test
    test = WebSocketCameraTest(camera_index, quality, fps)
    await test.connect_and_stream(duration)


if __name__ == "__main__":
    print("=" * 60)
    print("WebSocket Camera Stream Test")
    print("=" * 60)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
        import traceback

        traceback.print_exc()
