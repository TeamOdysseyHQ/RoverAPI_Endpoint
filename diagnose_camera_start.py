#!/usr/bin/env python3
"""
Camera Start Diagnostic Tool

Tests the camera start endpoint and provides detailed debugging information.
"""

import requests
import sys
import json


def test_camera_start(camera_index=0, width=1280, height=720, fps=30):
    """Test starting a camera with detailed output"""
    base_url = "http://localhost:6767"

    print(f"=" * 60)
    print(f"Camera Start Diagnostic Tool")
    print(f"=" * 60)
    print()

    # Step 1: Check if backend is running
    print("Step 1: Checking backend health...")
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            print("✓ Backend is running")
        else:
            print(f"✗ Backend returned status {response.status_code}")
            return
    except requests.exceptions.RequestException as e:
        print(f"✗ Backend is not running: {e}")
        print("  → Start backend with: cd endpoint && uv run main.py")
        return

    print()

    # Step 2: Detect cameras
    print("Step 2: Detecting cameras...")
    try:
        response = requests.get(f"{base_url}/api/nav/cameras/detect", timeout=10)
        if response.status_code == 200:
            data = response.json()
            cameras = data.get("cameras", [])
            print(f"✓ Found {len(cameras)} camera(s)")
            for cam in cameras:
                print(f"  - Camera {cam['index']}: {cam.get('name', 'Unknown')}")
                print(f"    Path: {cam.get('path', 'N/A')}")
                print(f"    Backend: {cam.get('backend', 'N/A')}")

            if not cameras:
                print("  → No cameras found. Check USB connections:")
                print("     ls -la /dev/video*")
                return

            if camera_index >= len(cameras):
                print(f"  → Camera {camera_index} not available")
                return
        else:
            print(f"✗ Detect failed with status {response.status_code}")
            print(f"  Response: {response.text}")
            return
    except Exception as e:
        print(f"✗ Failed to detect cameras: {e}")
        return

    print()

    # Step 3: Start camera
    print(f"Step 3: Starting camera {camera_index}...")
    print(f"  Parameters: {width}x{height} @ {fps}fps")
    try:
        form_data = {"width": width, "height": height, "fps": fps}
        response = requests.post(
            f"{base_url}/api/nav/cameras/{camera_index}/start",
            data=form_data,
            timeout=10,
        )

        print(f"  Status Code: {response.status_code}")
        print(f"  Response Headers: {dict(response.headers)}")
        print(f"  Response Body:")

        try:
            data = response.json()
            print(json.dumps(data, indent=2))

            if response.status_code == 200:
                print()
                print("✓ Camera started successfully!")
            else:
                print()
                print(f"✗ Camera start failed with status {response.status_code}")
                if "detail" in data:
                    print(f"  Error: {data['detail']}")
        except json.JSONDecodeError:
            print(f"  (Raw) {response.text}")

    except requests.exceptions.Timeout:
        print("✗ Request timed out")
        print("  → Camera might be taking too long to open")
        print("  → Check if camera is in use by another process:")
        print("     fuser /dev/video0")
    except Exception as e:
        print(f"✗ Failed to start camera: {e}")
        return

    print()

    # Step 4: Check camera status
    print(f"Step 4: Checking camera {camera_index} status...")
    try:
        response = requests.get(
            f"{base_url}/api/nav/cameras/{camera_index}/status", timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            camera_status = data.get("camera", {})
            print(json.dumps(camera_status, indent=2))

            if camera_status.get("active"):
                print()
                print("✓ Camera is active and ready!")
                print()
                print("Next steps:")
                print("  1. Open dashboard: http://localhost:5173")
                print("  2. Click 'Detect' to find cameras")
                print("  3. Click 'Start Camera' button")
                print("  4. Check browser console (F12) for errors")
            else:
                print()
                print("✗ Camera is not active after start")
        else:
            print(f"✗ Status check failed with status {response.status_code}")
    except Exception as e:
        print(f"✗ Failed to check status: {e}")

    print()
    print("=" * 60)
    print("Diagnostic Complete")
    print("=" * 60)


if __name__ == "__main__":
    camera_index = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 1280
    height = int(sys.argv[3]) if len(sys.argv) > 3 else 720
    fps = int(sys.argv[4]) if len(sys.argv) > 4 else 30

    test_camera_start(camera_index, width, height, fps)
