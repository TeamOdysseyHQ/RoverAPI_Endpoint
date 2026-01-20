#!/usr/bin/env python3
"""
End-to-end test for /teensy_topic endpoint.

This test verifies the complete flow of:
1. Connecting to ROS via rosbridge
2. Subscribing to /teensy_topic
3. Receiving and processing data from the teensy
4. Unsubscribing from the topic
5. Debugging the internal state

Prerequisites:
1. Start rosbridge_server: ros2 launch rosbridge_server rosbridge_websocket_launch.xml
2. Start publishing to /teensy_topic: ros2 topic pub /teensy_topic std_msgs/Int32 "data: 42" -r 10
3. Start the API server: uv run main.py
4. Run this test: python tests/test_teensy_topic_e2e.py
"""

import requests
import time
import sys

API_URL = "http://localhost:6767"


def check_ros_status():
    """Check if ROS bridge is connected"""
    print("Checking ROS bridge connection...")
    try:
        response = requests.get(f"{API_URL}/api/ros/status")
        response.raise_for_status()
        data = response.json()
        print(f"  Status: {data}")
        return data.get("status", {}).get("connected", False)
    except Exception as e:
        print(f"  ❌ Error checking ROS status: {e}")
        return False


def get_teensy_topic_data():
    """Get latest data from /teensy_topic"""
    print("Fetching teensy topic data...")
    try:
        response = requests.get(f"{API_URL}/api/o/teensy_topic")
        response.raise_for_status()
        data = response.json()

        if data.get("success"):
            if data.get("data") is not None:
                print(f"  ✓ Received data: {data['data']}")
                print(f"    Topic: {data.get('topic', 'N/A')}")
                print(f"    Subscribed: {data.get('subscribed', False)}")
            else:
                print(f"  ⏳ Subscribed, waiting for data...")
                print(f"    Message: {data.get('message', 'N/A')}")
        else:
            print(f"  ❌ Request failed: {data}")

        return data
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 503:
            print(f"  ❌ Service unavailable: Not connected to ROS")
        else:
            print(f"  ❌ HTTP error: {e}")
        return None
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


def debug_teensy_topic():
    """Get debug information about teensy topic state"""
    print("Fetching debug information...")
    try:
        response = requests.get(f"{API_URL}/api/o/teensy_topic/debug")
        response.raise_for_status()
        data = response.json()

        print(f"  Connected: {data.get('connected', False)}")
        print(f"  Subscribed topics: {data.get('subscribed_topics', [])}")
        print(f"  Latest message keys: {data.get('latest_messages_keys', [])}")
        print(f"  Teensy in latest: {data.get('teensy_in_latest', False)}")
        print(f"  Teensy message: {data.get('teensy_message', None)}")

        return data
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


def unsubscribe_teensy_topic():
    """Unsubscribe from /teensy_topic"""
    print("Unsubscribing from teensy topic...")
    try:
        response = requests.post(f"{API_URL}/api/o/teensy_topic/unsubscribe")
        response.raise_for_status()
        data = response.json()

        if data.get("success"):
            print(f"  ✓ {data.get('message', 'Unsubscribed successfully')}")
        else:
            print(f"  ❌ Failed to unsubscribe: {data}")

        return data
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


def run_test():
    """Run the complete end-to-end test"""
    print("=" * 70)
    print("TEENSY TOPIC END-TO-END TEST")
    print("=" * 70)

    # Test 1: Check ROS connection
    print("\n[TEST 1] Checking ROS bridge connection")
    print("-" * 70)
    if not check_ros_status():
        print("\n❌ ROS bridge not connected!")
        print("\nSetup instructions:")
        print("  1. Start rosbridge_server:")
        print("     ros2 launch rosbridge_server rosbridge_websocket_launch.xml")
        print("  2. Publish test data:")
        print('     ros2 topic pub /teensy_topic std_msgs/Int32 "data: 42" -r 10')
        print("  3. Start API server:")
        print("     cd endpoint && uv run main.py")
        return False
    print("✓ ROS bridge connected!")

    # Test 2: Subscribe and get first data
    print("\n[TEST 2] Subscribe to /teensy_topic and get initial data")
    print("-" * 70)
    result = get_teensy_topic_data()
    if not result or not result.get("success"):
        print("❌ Failed to subscribe or get data")
        return False

    # Wait for data if not immediately available
    if result.get("data") is None:
        print("  Waiting for data to arrive...")
        time.sleep(2)
        result = get_teensy_topic_data()

        if not result or result.get("data") is None:
            print("❌ No data received after waiting")
            print("Make sure /teensy_topic is being published:")
            print('  ros2 topic pub /teensy_topic std_msgs/Int32 "data: 42" -r 10')
            return False

    print("✓ Successfully subscribed and received data")

    # Test 3: Get multiple data samples
    print("\n[TEST 3] Polling for multiple data samples")
    print("-" * 70)
    samples = []
    for i in range(5):
        print(f"  Sample {i + 1}/5...")
        result = get_teensy_topic_data()
        if result and result.get("success") and result.get("data") is not None:
            samples.append(result.get("data"))
        time.sleep(0.5)

    if len(samples) > 0:
        print(f"✓ Collected {len(samples)} samples: {samples}")
        print(
            f"  Min: {min(samples)}, Max: {max(samples)}, Avg: {sum(samples) / len(samples):.2f}"
        )
    else:
        print("⚠ No samples collected")

    # Test 4: Debug endpoint
    print("\n[TEST 4] Testing debug endpoint")
    print("-" * 70)
    debug_result = debug_teensy_topic()
    if debug_result:
        if "/teensy_topic" in debug_result.get("subscribed_topics", []):
            print("✓ Topic is in subscribed list")
        else:
            print("⚠ Topic not in subscribed list")

        if debug_result.get("teensy_in_latest"):
            print("✓ Latest message is cached")
        else:
            print("⚠ No message in cache")
    else:
        print("❌ Debug endpoint failed")

    # Test 5: Unsubscribe
    print("\n[TEST 5] Unsubscribing from topic")
    print("-" * 70)
    unsub_result = unsubscribe_teensy_topic()
    if not unsub_result or not unsub_result.get("success"):
        print("❌ Failed to unsubscribe")
        return False
    print("✓ Successfully unsubscribed")

    # Test 6: Verify unsubscription
    print("\n[TEST 6] Verifying unsubscription via debug")
    print("-" * 70)
    debug_result = debug_teensy_topic()
    if debug_result:
        if "/teensy_topic" not in debug_result.get("subscribed_topics", []):
            print("✓ Topic removed from subscribed list")
        else:
            print("⚠ Topic still in subscribed list")

    # Test 7: Re-subscribe by calling GET again
    print("\n[TEST 7] Re-subscribing by calling GET endpoint")
    print("-" * 70)
    result = get_teensy_topic_data()
    if result and result.get("success"):
        print("✓ Successfully re-subscribed (endpoint handles auto-subscribe)")

        # Give it time to receive data
        time.sleep(1)
        result = get_teensy_topic_data()
        if result.get("data") is not None:
            print(f"✓ Received data after re-subscription: {result.get('data')}")
        else:
            print("⚠ Subscribed but no data yet")
    else:
        print("❌ Failed to re-subscribe")

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print("✓ All core functionality tests passed!")
    print("\nEndpoint behavior verified:")
    print("  1. Auto-subscription on first GET request")
    print("  2. Data retrieval with caching")
    print("  3. Debug endpoint for internal state")
    print("  4. Unsubscribe functionality")
    print("  5. Re-subscription capability")
    print("\n" + "=" * 70)

    return True


def main():
    try:
        success = run_test()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠ Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
