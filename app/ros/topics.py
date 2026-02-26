"""Standard ROS2 topic names for rover subsystems"""

# Navigation topics
CMD_VEL_TOPIC = "/cmd_vel"
ODOM_TOPIC = "/odom"
ODOMETRY_TOPIC = ODOM_TOPIC  # Alias for backward compatibility
GOAL_POSE_TOPIC = "/goal_pose"
TEST_TOPIC = "/teensy_topic"
MOTOR_RPM_TOPIC = "/motor_rpms"  # Float32MultiArray[6] - per-wheel RPMs (FL, FR, ML, MR, RL, RR)

# Camera topics
CAMERA_IMAGE_PREFIX = "/camera"
CAMERA_COLOR_IMAGE_RAW_TOPIC = "/camera/camera/color/image_raw"

# Diagnostics topics
DIAGNOSTICS_TOPIC = "/diagnostics"
BATTERY_TOPIC = "/battery_state"

# Arm topics (matching micro-ROS topics in ARM/src/RosArmBridge.cpp)
ARM_TELEMETRY_TOPIC = (
    "arm/telemetry"  # std_msgs/String - CSV: stepper[2], dc[2], servo[2], ch[6]
)
ARM_COMMAND_TOPIC = "arm/command"  # std_msgs/Int32 - Commands: 1=drop, -1=stop
ARM_TARGET_TOPIC = "arm/target"  # std_msgs/Float32MultiArray - 6 target angles

# Science topics (matching Teensy PubSub.cpp)
SCIENCE_DATA_TOPIC = "science_sensor_data"  # Float32MultiArray[14] - sensor readings
SCIENCE_DRILL_DATA_TOPIC = (
    "science_drill_data"  # Float32MultiArray[8] - drill telemetry
)
SCIENCE_INFO_WARNING_TOPIC = "science_info_warning"  # Int32 - warning/alert codes
SCIENCE_CONTROL_TOPIC = "/science_control"  # Int32MultiArray[5] - control commands
