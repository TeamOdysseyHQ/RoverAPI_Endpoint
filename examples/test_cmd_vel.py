#!/usr/bin/env python3
"""
Example script to test ROS integration via the API.
This script demonstrates how to send velocity commands to the rover.

Prerequisites:
1. Start rosbridge_server: ros2 launch rosbridge_server rosbridge_websocket_launch.xml
2. Start the API server: uv run main.py
3. Run this script: python examples/test_cmd_vel.py
"""

import requests
import time

API_URL = "http://localhost:6767"


def check_ros_status():
    """Check if ROS bridge is connected"""
    response = requests.get(f"{API_URL}/api/ros/status")
    data = response.json()
    print(f"ROS Status: {data}")
    return data["status"]["connected"]


def send_velocity(linear_x=0.0, angular_z=0.0):
    """Send velocity command to rover"""
    payload = {
        "linear_x": linear_x,
        "linear_y": 0.0,
        "linear_z": 0.0,
        "angular_x": 0.0,
        "angular_y": 0.0,
        "angular_z": angular_z,
    }

    response = requests.post(f"{API_URL}/api/nav/ros/cmd_vel", json=payload)
    data = response.json()
    print(f"Velocity command: linear_x={linear_x}, angular_z={angular_z}")
    print(f"Response: {data}")
    return data["success"]


def stop_rover():
    """Send stop command"""
    response = requests.post(f"{API_URL}/api/nav/ros/cmd_vel/stop")
    data = response.json()
    print(f"Stop command sent: {data}")
    return data["success"]


def subscribe_odometry():
    """Subscribe to odometry topic"""
    response = requests.post(f"{API_URL}/api/nav/ros/odom/subscribe")
    data = response.json()
    print(f"Odometry subscription: {data}")
    return data["success"]


def get_odometry():
    """Get latest odometry data"""
    response = requests.get(f"{API_URL}/api/nav/ros/odom")
    data = response.json()
    if data["success"] and data["data"]:
        pose = data["data"]["pose"]["pose"]
        print(
            f"Current position: x={pose['position']['x']:.2f}, y={pose['position']['y']:.2f}, z={pose['position']['z']:.2f}"
        )
    else:
        print("No odometry data available yet")
    return data


def main():
    print("=" * 60)
    print("ROS Integration Test - Velocity Commands")
    print("=" * 60)

    # Check ROS connection
    print("\n1. Checking ROS bridge connection...")
    if not check_ros_status():
        print("❌ ROS bridge not connected!")
        print("   Make sure rosbridge_server is running:")
        print("   ros2 launch rosbridge_server rosbridge_websocket_launch.xml")
        return
    print("✓ ROS bridge connected!")

    # Subscribe to odometry
    print("\n2. Subscribing to odometry...")
    subscribe_odometry()

    # Move forward
    print("\n3. Moving forward for 2 seconds...")
    send_velocity(linear_x=1.0, angular_z=0.0)
    time.sleep(2)

    # Stop
    print("\n4. Stopping...")
    stop_rover()
    time.sleep(1)

    # Rotate
    print("\n5. Rotating for 2 seconds...")
    send_velocity(linear_x=0.0, angular_z=0.5)
    time.sleep(2)

    # Stop
    print("\n6. Stopping...")
    stop_rover()
    time.sleep(1)

    # Get odometry
    print("\n7. Getting odometry data...")
    get_odometry()

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
