"""Standard ROS2 topic names for rover subsystems"""

# Navigation topics
CMD_VEL_TOPIC = "/cmd_vel"
ODOM_TOPIC = "/odom"
GOAL_POSE_TOPIC = "/goal_pose"
TEST_TOPIC = "/teensy_topic"

# Camera topics
CAMERA_IMAGE_PREFIX = "/camera"

# Diagnostics topics
DIAGNOSTICS_TOPIC = "/diagnostics"
BATTERY_TOPIC = "/battery_state"

# Arm topics (matching micro-ROS topics in ARM/src/RosArmBridge.cpp)
ARM_TELEMETRY_TOPIC = (
    "arm/telemetry"  # std_msgs/String - CSV: stepper[2], dc[2], servo[2], ch[6]
)
ARM_COMMAND_TOPIC = "arm/command"  # std_msgs/Int32 - Commands: 1=drop, -1=stop
ARM_TARGET_TOPIC = "arm/target"  # std_msgs/Float32MultiArray - 6 target angles

# Science topics
SCIENCE_DATA_TOPIC = "/science_sensor_data"
