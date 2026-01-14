# RoverAPI Endpoint
This repository is the API endpoint primarily for the rover's onboard computer with integrated ROS2 support via rosbridge. This document will brief you about accessing, contributing and utilizing this repository.

# Setup
Use uv for dependency management.

Initial setup command:
```sh
uv sync
```

Expose the port over the entire network for other machines to connect to:
```sh
uv run main.py
```

For the dashboard devs, use the URL `http://<IP-Addr>:6767/<endpoint>`


## ROS2 Integration

This endpoint integrates with ROS2 through rosbridge WebSocket for bidirectional communication.

### Prerequisites

1. **ROS2 Installation** (Humble, Iron, or Jazzy recommended)
2. **rosbridge_suite** package:
   ```sh
   sudo apt install ros-${ROS_DISTRO}-rosbridge-suite
   ```

### Starting rosbridge_server

Before starting the API server, launch rosbridge_server in a separate terminal:

```sh
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

By default, rosbridge runs on `ws://localhost:9090`. You can configure this with environment variables (see below).

### Environment Configuration

Create a `.env` file in the project root (optional, defaults provided):

```env
ROSBRIDGE_HOST=localhost
ROSBRIDGE_PORT=9090
ROSBRIDGE_RETRY_INTERVAL=5
ROSBRIDGE_MAX_RETRIES=10
```

### ROS Topics Used

The API publishes and subscribes to the following standard ROS2 topics:

- `/cmd_vel` (geometry_msgs/Twist) - Velocity commands (published)
- `/odom` (nav_msgs/Odometry) - Odometry data (subscribed)

### Testing the Integration

1. **Start rosbridge_server**:
   ```sh
   ros2 launch rosbridge_server rosbridge_websocket_launch.xml
   ```

2. **Start the API server**:
   ```sh
   uv run main.py
   ```

3. **Check ROS connection status**:
   ```sh
   curl http://localhost:6767/api/ros/status
   ```

4. **Send a velocity command** (move forward):
   ```sh
   curl -X POST http://localhost:6767/api/nav/ros/cmd_vel \
     -H "Content-Type: application/json" \
     -d '{"linear_x": 1.0, "angular_z": 0.0}'
   ```

5. **Stop the rover**:
   ```sh
   curl -X POST http://localhost:6767/api/nav/ros/cmd_vel/stop
   ```

6. **Subscribe to odometry and get data**:
   ```sh
   # Subscribe first
   curl -X POST http://localhost:6767/api/nav/ros/odom/subscribe
   
   # Then get latest data
   curl http://localhost:6767/api/nav/ros/odom
   ```

### Monitoring from ROS side

You can monitor the topics from ROS2 command line:

```sh
# List active topics
ros2 topic list

# Echo velocity commands being published
ros2 topic echo /cmd_vel

# Manually publish to test (the example you provided)
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 1.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
```


## Reading/Accessing/Using
Always perform POST requests to specific endpoints. All supported endpoints will be provided by the *available* endpoint.

### End points
* **/api/nav/**: Backend endpoint(s) for navigation subsystem
* **/api/nav/ros/**: ROS2 integration for navigation (cmd_vel, odom)
* **/api/dgt/**: Backend endpoint(s) for diagnostics
* **/api/sci/**: Backend endpoint(s) for science subsystem
* **/api/arm/**: Backend endpoint(s) for arm subsystem
* **/api/o/**: Additional endpoint(s) provided
* **/api/ros/**: ROS bridge status and control endpoints

### New ROS Endpoints

**Navigation ROS Endpoints** (`/api/nav/ros/`):
- `POST /cmd_vel` - Publish velocity commands to move the rover
- `POST /cmd_vel/stop` - Emergency stop (publish zero velocities)
- `POST /odom/subscribe` - Subscribe to odometry topic
- `GET /odom` - Get latest odometry data
- `POST /publish` - Publish custom messages to any topic

**ROS Status Endpoints** (`/api/ros/`):
- `GET /status` - Get rosbridge connection status
- `POST /connect` - Manually connect to rosbridge
- `POST /disconnect` - Disconnect from rosbridge

## Developer/Contributor documentation

Some general guidelines:
* **Always fork the repository and make a pull request**
* Do not write/support *GET* requests for backend unless its required (eg: downloads).
* Type annotations are always better to be provided. Support complex type annotation by adding them to [types files](app/py_types.py) which contains an example.
* Always update available.py files if any new endpoint is added
* Follow the directory structure and update the [main server script](app/__init__.py)
* Provide minimum amount of comments to explain ***why your code exists*** rather than **how it works**. Its easy to understand that certain part of code is a loop as opposed to understanding why we need the loop.

### Directory Structure
Most directory names are self explanatory but here is a quick reference,
* [Arm Directory](app/api/arm/): Backend Files for the arm subsystem.
* [Diagnostics Directory](app/api/diagnostics/): Backend Files for running diagnostics/check-ups on rover.
* [Navigation Directory](app/api/navigation/): Backend Files for the navigation subsystem and most of scouting modules.
* [Science Directory](app/api/science/): Backend Files for the science subsystem and any analytical modules.
* [ROS Directory](app/ros/): ROS2 integration via rosbridge WebSocket.

* [Others Directory](app/api/others/): Additional endpoints for debugging, logging etc.

