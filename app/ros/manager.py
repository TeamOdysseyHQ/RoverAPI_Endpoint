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
            self.client.on("close", self._on_close)

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

    # MOTOR RPM convenience methods

    def subscribe_motor_rpms(self, callback: Optional[Callable] = None) -> bool:
        """Subscribe to motor RPM topic (/motor_rpms)"""
        return self.subscribe(MOTOR_RPM_TOPIC, "std_msgs/Float32MultiArray", callback)

    def get_latest_motor_rpms(self) -> Optional[Dict[str, Any]]:
        """
        Get latest motor RPM data and parse Float32MultiArray.

        Returns parsed motor RPMs with structure:
        {
            "front_left": float,
            "front_right": float,
            "mid_left": float,
            "mid_right": float,
            "rear_left": float,
            "rear_right": float,
            "raw": list[float]
        }
        """
        raw_message = self.get_latest_message(MOTOR_RPM_TOPIC)
        if raw_message is None:
            return None

        data = raw_message.get("data", [])
        if len(data) < 6:
            print(f"Warning: Expected 6 values in motor RPM data, got {len(data)}")
            return None

        return {
            "front_left": float(data[0]),
            "front_right": float(data[1]),
            "mid_left": float(data[2]),
            "mid_right": float(data[3]),
            "rear_left": float(data[4]),
            "rear_right": float(data[5]),
            "raw": [float(v) for v in data],
        }

    # ARM convenience methods

    def publish_arm_command(self, command: int) -> bool:
        """
        Publish command to arm/command topic.

        Args:
            command: Command code (1 = drop payload, -1 = emergency stop)

        Returns:
            True if published successfully
        """
        message = {"data": command}
        return self.publish(ARM_COMMAND_TOPIC, "std_msgs/Int32", message)

    def publish_arm_target(
        self,
        dc_elbow: float,
        dc_wrist_pitch: float,
        stepper_base_pan: float,
        stepper_shoulder: float,
        servo_wrist_roll: float,
        servo_gripper: float,
    ) -> bool:
        """
        Publish target angles to arm/target topic.

        Args:
            dc_elbow: Target angle for DC motor 1 (elbow)
            dc_wrist_pitch: Target angle for DC motor 2 (wrist pitch)
            stepper_base_pan: Target angle for stepper 1 (base pan)
            stepper_shoulder: Target angle for stepper 2 (shoulder)
            servo_wrist_roll: Target angle for servo 1 (wrist roll)
            servo_gripper: Target angle for servo 2 (gripper)

        Returns:
            True if published successfully
        """
        # ARM expects: [dc0, dc1, stepper0, stepper1, servo0, servo1]
        message = {
            "data": [
                dc_elbow,
                dc_wrist_pitch,
                stepper_base_pan,
                stepper_shoulder,
                servo_wrist_roll,
                servo_gripper,
            ]
        }
        return self.publish(ARM_TARGET_TOPIC, "std_msgs/Float32MultiArray", message)

    def subscribe_arm_telemetry(self, callback: Optional[Callable] = None) -> bool:
        """Subscribe to arm/telemetry topic"""
        return self.subscribe(ARM_TELEMETRY_TOPIC, "std_msgs/String", callback)

    def get_latest_arm_telemetry(self) -> Optional[Dict[str, Any]]:
        """
        Get latest arm telemetry message and parse CSV format.

        Returns parsed telemetry with structure:
        {
            "stepper": {"base_pan": float, "shoulder": float},
            "dc": {"elbow": float, "wrist_pitch": float},
            "servo": {"wrist_roll": float, "gripper": float},
            "rc_channels": {"ch1": int, "ch2": int, "ch3": int, "ch4": int, "ch5": int, "ch6": int},
            "raw": str  # Original CSV string
        }
        """
        raw_message = self.get_latest_message(ARM_TELEMETRY_TOPIC)
        if raw_message is None:
            return None

        # Extract CSV string from std_msgs/String message
        csv_data = raw_message.get("data", "")
        if not csv_data:
            return None

        try:
            # Parse CSV: stepper[0], stepper[1], dc[0], dc[1], servo[0], servo[1], ch1, ch2, ch3, ch4, ch5, ch6
            values = [float(v.strip()) for v in csv_data.split(",")]

            if len(values) < 12:
                print(f"Warning: Expected 12 values in telemetry, got {len(values)}")
                return None

            return {
                "stepper": {
                    "base_pan": values[0],
                    "shoulder": values[1],
                },
                "dc": {
                    "elbow": values[2],
                    "wrist_pitch": values[3],
                },
                "servo": {
                    "wrist_roll": values[4],
                    "gripper": values[5],
                },
                "rc_channels": {
                    "ch1": int(values[6]),
                    "ch2": int(values[7]),
                    "ch3": int(values[8]),
                    "ch4": int(values[9]),
                    "ch5": int(values[10]),
                    "ch6": int(values[11]),
                },
                "raw": csv_data,
            }

        except (ValueError, IndexError) as e:
            print(f"Failed to parse arm telemetry CSV: {e}")
            return None

    # SCIENCE convenience methods

    def publish_science_control(
        self,
        linear_actuator_cmd: int = -6,
        drill_cmd: int = -6,
        barrel_cmd: int = -6,
        servo_toggle: bool = False,
        science_module_toggle: bool = False,
    ) -> bool:
        """
        Publish control command to science module.

        Args:
            linear_actuator_cmd: -1=down, 1=up, 0/4/8/16=microstep modes, -6=no command
            drill_cmd: -2=CW, -1=decrease speed, 0=stop, 1=increase speed, 2=CCW, -6=no command
            barrel_cmd: 1=rotate 60°, 0/4/8/16=microstep modes, -6=no command
            servo_toggle: Toggle PH servo position
            science_module_toggle: Enable/disable science exploration mode

        Returns:
            True if published successfully
        """
        message = {
            "data": [
                linear_actuator_cmd,
                drill_cmd,
                barrel_cmd,
                # IF DROP THE TEST TUBE button is pressed, send 2 in servo toggle position
                (1 if servo_toggle else 0),
                1 if science_module_toggle else 0,
            ]
        }
        return self.publish(SCIENCE_CONTROL_TOPIC, "std_msgs/Int32MultiArray", message)

    def subscribe_drill_data(self, callback: Optional[Callable] = None) -> bool:
        """Subscribe to drill telemetry topic (distance, IMU, current)"""
        return self.subscribe(
            SCIENCE_DRILL_DATA_TOPIC, "std_msgs/Float32MultiArray", callback
        )

    def get_latest_drill_data(self) -> Optional[Dict[str, Any]]:
        """
        Get latest drill telemetry message and parse Float32MultiArray.

        Returns parsed drill data with structure:
        {
            "drill_halted": bool,
            "distance_mm": float,
            "accelerometer": {"x": float, "y": float, "z": float},
            "gyroscope": {"x": float, "y": float, "z": float}
        }
        """
        raw_message = self.get_latest_message(SCIENCE_DRILL_DATA_TOPIC)
        if raw_message is None:
            return None

        data = raw_message.get("data", [])
        if len(data) < 8:
            print(f"Warning: Expected 8 values in drill data, got {len(data)}")
            return None

        return {
            "drill_halted": bool(data[0]),
            "distance_mm": float(data[1]),
            "accelerometer": {
                "x": float(data[2]),
                "y": float(data[3]),
                "z": float(data[4]),
            },
            "gyroscope": {
                "x": float(data[5]),
                "y": float(data[6]),
                "z": float(data[7]),
            },
        }

    def subscribe_science_warnings(self, callback: Optional[Callable] = None) -> bool:
        """Subscribe to science info/warning codes"""
        return self.subscribe(SCIENCE_INFO_WARNING_TOPIC, "std_msgs/Int32", callback)

    def get_latest_science_warning(self) -> Optional[int]:
        """
        Get latest science warning code.

        Warning codes:
        1 = Start drilling
        2 = Stop drilling (depth limit reached)
        3 = Shake detected
        4 = Current threshold 1 exceeded
        5 = Current threshold 2 exceeded (drill auto-stopped)
        """
        raw_message = self.get_latest_message(SCIENCE_INFO_WARNING_TOPIC)
        if raw_message is None:
            return None

        return raw_message.get("data")

    # CAMERA convenience methods

    def subscribe_camera_image(
        self, topic_name: Optional[str] = None, callback: Optional[Callable] = None
    ) -> bool:
        """
        Subscribe to camera image topic.

        Args:
            topic_name: Camera topic name (default: /camera/camera/color/image_raw)
            callback: Optional callback function to handle image messages

        Returns:
            True if subscribed successfully
        """
        if topic_name is None:
            topic_name = CAMERA_COLOR_IMAGE_RAW_TOPIC

        return self.subscribe(topic_name, "sensor_msgs/Image", callback)

    def get_latest_camera_image(
        self, topic_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get latest camera image message.

        Args:
            topic_name: Camera topic name (default: /camera/camera/color/image_raw)

        Returns:
            Image message with structure:
            {
                "header": {"seq": int, "stamp": {...}, "frame_id": str},
                "height": int,
                "width": int,
                "encoding": str,  # e.g., "rgb8", "bgr8", "mono8"
                "is_bigendian": int,
                "step": int,  # row length in bytes
                "data": str  # base64 encoded image data
            }
        """
        if topic_name is None:
            topic_name = CAMERA_COLOR_IMAGE_RAW_TOPIC

        return self.get_latest_message(topic_name)


# Global instance
ros_manager = RosbridgeManager()
