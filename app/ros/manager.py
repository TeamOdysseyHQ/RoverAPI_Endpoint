"""ROS bridge manager for WebSocket communication with rosbridge_server"""

import roslibpy
import threading
import time
from typing import Optional, Dict, Any, Callable
from app.ros.config import config
from app.ros.topics import *


class RosbridgeManager:
    """
    Singleton manager for rosbridge WebSocket connections.
    Handles connection lifecycle, publishing, subscribing, and reconnection.
    """

    _instance: Optional["RosbridgeManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Only initialize once
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self.config = config
        self.client: Optional[roslibpy.Ros] = None
        self.is_connected = False
        self._subscribers: Dict[str, roslibpy.Topic] = {}
        self._publishers: Dict[str, roslibpy.Topic] = {}
        self._latest_messages: Dict[
            str, Any
        ] = {}  # Cache latest messages from subscriptions

    def connect(self) -> bool:
        """
        Connect to rosbridge server.
        Returns True if connection successful, False otherwise.
        """
        if self.client and self.is_connected:
            return True

        try:
            self.client = roslibpy.Ros(host=self.config.host, port=self.config.port)
            self.client.on_ready(self._on_ready)
            self.client.on('close', self._on_close)

            self.client.run()

            # Wait for connection (with timeout)
            timeout = 5
            start_time = time.time()
            while not self.is_connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)

            return self.is_connected

        except Exception as e:
            print(f"Failed to connect to rosbridge: {e}")
            self.is_connected = False
            return False

    def _on_ready(self):
        """Callback when connection is established"""
        self.is_connected = True
        print(f"✓ Connected to rosbridge at {self.config.url}")

    def _on_close(self):
        """Callback when connection is closed"""
        self.is_connected = False
        print("✗ Disconnected from rosbridge")

    def disconnect(self):
        """Disconnect from rosbridge server"""
        if self.client:
            # Unsubscribe all topics
            for topic in self._subscribers.values():
                topic.unsubscribe()
            self._subscribers.clear()

            # Unadvertise all publishers
            for topic in self._publishers.values():
                topic.unadvertise()
            self._publishers.clear()

            # Close connection
            self.client.close()
            self.is_connected = False
            self.client = None

    def publish(
        self, topic_name: str, message_type: str, message: Dict[str, Any]
    ) -> bool:
        """
        Publish a message to a ROS topic.

        Args:
            topic_name: Name of the topic (e.g., "/cmd_vel")
            message_type: ROS message type (e.g., "geometry_msgs/Twist")
            message: Message data as dictionary

        Returns:
            True if published successfully, False otherwise
        """
        if not self.is_connected:
            print("Not connected to rosbridge. Cannot publish.")
            return False

        try:
            # Get or create publisher
            if topic_name not in self._publishers:
                self._publishers[topic_name] = roslibpy.Topic(
                    self.client, topic_name, message_type
                )
                self._publishers[topic_name].advertise()

            # Publish message
            self._publishers[topic_name].publish(roslibpy.Message(message))
            return True

        except Exception as e:
            print(f"Failed to publish to {topic_name}: {e}")
            return False

    def subscribe(
        self, topic_name: str, message_type: str, callback: Optional[Callable] = None
    ) -> bool:
        """
        Subscribe to a ROS topic.

        Args:
            topic_name: Name of the topic (e.g., "/odom")
            message_type: ROS message type (e.g., "nav_msgs/Odometry")
            callback: Optional callback function to handle messages

        Returns:
            True if subscribed successfully, False otherwise
        """
        if not self.is_connected:
            print("Not connected to rosbridge. Cannot subscribe.")
            return False

        try:
            # Don't subscribe twice
            if topic_name in self._subscribers:
                return True

            # Create subscription
            topic = roslibpy.Topic(self.client, topic_name, message_type)

            # Default callback stores latest message
            def default_callback(message):
                self._latest_messages[topic_name] = message
                print(f"[ROS Manager] Received message on {topic_name}: {message}")
                if callback:
                    callback(message)

            topic.subscribe(default_callback)
            self._subscribers[topic_name] = topic

            return True

        except Exception as e:
            print(f"Failed to subscribe to {topic_name}: {e}")
            return False

    def unsubscribe(self, topic_name: str):
        """Unsubscribe from a topic"""
        if topic_name in self._subscribers:
            self._subscribers[topic_name].unsubscribe()
            del self._subscribers[topic_name]
            if topic_name in self._latest_messages:
                del self._latest_messages[topic_name]

    def get_latest_message(self, topic_name: str) -> Optional[Dict[str, Any]]:
        """Get the latest message received on a subscribed topic"""
        return self._latest_messages.get(topic_name)

    def get_status(self) -> Dict[str, Any]:
        """Get connection status and info"""
        return {
            "connected": self.is_connected,
            "url": self.config.url,
            "subscribed_topics": list(self._subscribers.keys()),
            "published_topics": list(self._publishers.keys()),
        }

    # Convenience methods for common operations

    def publish_cmd_vel(
        self,
        linear_x: float = 0.0,
        linear_y: float = 0.0,
        linear_z: float = 0.0,
        angular_x: float = 0.0,
        angular_y: float = 0.0,
        angular_z: float = 0.0,
    ) -> bool:
        """
        Publish velocity command (Twist message) to /cmd_vel.

        Args:
            linear_x: Linear velocity in x direction (forward/backward)
            linear_y: Linear velocity in y direction (left/right)
            linear_z: Linear velocity in z direction (up/down)
            angular_x: Angular velocity around x axis (roll)
            angular_y: Angular velocity around y axis (pitch)
            angular_z: Angular velocity around z axis (yaw)

        Returns:
            True if published successfully
        """
        message = {
            "linear": {"x": linear_x, "y": linear_y, "z": linear_z},
            "angular": {"x": angular_x, "y": angular_y, "z": angular_z},
        }
        return self.publish(CMD_VEL_TOPIC, "geometry_msgs/Twist", message)

    def subscribe_odom(self, callback: Optional[Callable] = None) -> bool:
        """Subscribe to odometry topic"""
        return self.subscribe(ODOM_TOPIC, "nav_msgs/Odometry", callback)

    def get_latest_odom(self) -> Optional[Dict[str, Any]]:
        """Get latest odometry message"""
        return self.get_latest_message(ODOM_TOPIC)


# Global instance
ros_manager = RosbridgeManager()
