#!/usr/bin/env python3
"""
Example ROS2 subscriber to monitor cmd_vel commands sent by the API.
This demonstrates monitoring from the ROS side.

Prerequisites:
1. Start rosbridge_server: ros2 launch rosbridge_server rosbridge_websocket_launch.xml
2. Start the API server: uv run main.py
3. In another terminal, run this: ros2 topic echo /cmd_vel

Or run this Python script directly if rclpy is available:
"""

try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Twist

    class CmdVelMonitor(Node):
        def __init__(self):
            super().__init__("cmd_vel_monitor")
            self.subscription = self.create_subscription(
                Twist, "/cmd_vel", self.listener_callback, 10
            )
            self.subscription
            print("🎧 Listening for velocity commands on /cmd_vel...")
            print(
                "   Send commands using: curl -X POST http://localhost:6767/api/nav/ros/cmd_vel ..."
            )
            print()

        def listener_callback(self, msg):
            print(f"📡 Received cmd_vel:")
            print(
                f"   Linear:  x={msg.linear.x:.2f}, y={msg.linear.y:.2f}, z={msg.linear.z:.2f}"
            )
            print(
                f"   Angular: x={msg.angular.x:.2f}, y={msg.angular.y:.2f}, z={msg.angular.z:.2f}"
            )
            print()

    def main():
        rclpy.init()
        monitor = CmdVelMonitor()
        try:
            rclpy.spin(monitor)
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")
        finally:
            monitor.destroy_node()
            rclpy.shutdown()

    if __name__ == "__main__":
        main()

except ImportError:
    print("❌ rclpy not available. Use this command instead:")
    print("   ros2 topic echo /cmd_vel")
    print()
    print("Or install ROS2 Python packages:")
    print("   sudo apt install ros-${ROS_DISTRO}-rclpy")
