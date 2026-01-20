#!/usr/bin/env python3
"""Direct test of ROS manager teensy_topic subscription"""

import sys
import time
import asyncio

# Add app to path
sys.path.insert(0, '/home/administratror/Projects/RoverAPI_Endpoint')

from app.ros.manager import ros_manager
from app.ros.topics import TEST_TOPIC

async def test_teensy_topic():
    print("Testing teensy_topic subscription...")
    
    # Connect if not already connected
    if not ros_manager.is_connected:
        print("Connecting to ROS...")
        success = ros_manager.connect()
        if not success:
            print("Failed to connect!")
            return
        print("✓ Connected to ROS")
    else:
        print("✓ Already connected to ROS")
    
    # Subscribe to teensy_topic
    print(f"\nSubscribing to {TEST_TOPIC}...")
    if TEST_TOPIC not in ros_manager._subscribers:
        success = ros_manager.subscribe(TEST_TOPIC, "std_msgs/Int32")
        if not success:
            print("Failed to subscribe!")
            return
        print("✓ Subscribed")
    else:
        print("✓ Already subscribed")
    
    # Wait for messages
    print("\nWaiting for messages (5 seconds)...")
    for i in range(10):
        await asyncio.sleep(0.5)
        latest = ros_manager.get_latest_message(TEST_TOPIC)
        if latest:
            print(f"✓ Got message: {latest}")
            break
        else:
            print(f"  Waiting... ({i+1}/10)")
    
    # Final check
    final_message = ros_manager.get_latest_message(TEST_TOPIC)
    if final_message:
        print(f"\n✓ Final message: {final_message}")
    else:
        print("\n✗ No messages received!")
    
    # Check internal state
    print(f"\n_latest_messages dict: {ros_manager._latest_messages}")
    print(f"Subscribed topics: {list(ros_manager._subscribers.keys())}")

if __name__ == "__main__":
    asyncio.run(test_teensy_topic())
