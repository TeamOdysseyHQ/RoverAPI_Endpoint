"""Arduino integration endpoints for navigation subsystem"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.arduino.manager import arduino_manager


router = APIRouter()


class ArduinoCommandRequest(BaseModel):
    """Request model for Arduino commands"""

    command: str  # "W", "S", "A", "D", or "X"


class ArduinoDirectionRequest(BaseModel):
    """Request model for directional commands"""

    direction: str  # "forward", "backward", "left", "right", "stop"


@router.post("/arduino/connect")
async def connect_arduino():
    """
    Connect to Arduino via serial port.
    Must be called before sending any commands.
    """
    success = arduino_manager.connect()

    if not success:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to connect to Arduino at {arduino_manager.config.port}. "
            "Ensure Arduino is connected and port is correct.",
        )

    return {
        "success": True,
        "message": f"Connected to Arduino at {arduino_manager.config.port}",
        "config": {
            "port": arduino_manager.config.port,
            "baudrate": arduino_manager.config.baudrate,
        },
    }


@router.post("/arduino/disconnect")
async def disconnect_arduino():
    """
    Disconnect from Arduino.
    """
    arduino_manager.disconnect()
    return {"success": True, "message": "Disconnected from Arduino"}


@router.get("/arduino/status")
async def get_arduino_status():
    """
    Get Arduino connection status.
    Returns connection state and configuration info.
    """
    status = arduino_manager.get_status()
    return {
        "success": True,
        "connected": status["connected"],
        "port": status["port"],
        "baudrate": status["baudrate"],
    }


@router.post("/arduino/cmd")
async def send_command(cmd: ArduinoCommandRequest):
    """
    Send a command to Arduino.

    Valid command formats:
    1. Single character commands:
       - W/w: Forward/Up
       - S/s: Backward/Down
       - A/a: Left
       - D/d: Right
       - X/x: Stop
       - I/i, J/j, K/k, L/l: Camera controls

    2. Speed-aware commands (format: "direction:speed"):
       - "w:255": Forward at speed 255 (0-255)
       - "s:120": Backward at speed 120
       - "a:200": Left at speed 200
       - "d:180": Right at speed 180
       - "x:0": Stop (speed 0)

    Example requests:
    ```json
    {
        "command": "W"
    }
    ```
    ```json
    {
        "command": "w:255"
    }
    ```
    """
    if not arduino_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to Arduino. Call POST /api/nav/arduino/connect first.",
        )

    success = arduino_manager.send_command(cmd.command)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to send command to Arduino")

    return {
        "success": True,
        "message": f"Command '{cmd.command}' sent to Arduino",
        "command": cmd.command,
    }


@router.post("/arduino/direction")
async def send_direction(cmd: ArduinoDirectionRequest):
    """
    Send a directional command to Arduino using friendly names.

    Valid directions:
    - forward: Move forward (W)
    - backward: Move backward (S)
    - left: Turn left (A)
    - right: Turn right (D)
    - stop: Stop movement (X)

    Example request:
    ```json
    {
        "direction": "forward"
    }
    ```
    """
    if not arduino_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to Arduino. Call POST /api/nav/arduino/connect first.",
        )

    # Map direction names to commands
    direction_map = {
        "forward": "w",
        "backward": "s",
        "left": "a",
        "right": "d",
        "stop": "x",
    }

    direction_lower = cmd.direction.lower()
    if direction_lower not in direction_map:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid direction: {cmd.direction}. "
            f"Valid directions: {list(direction_map.keys())}",
        )

    command = direction_map[direction_lower]
    success = arduino_manager.send_command(command)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to send command to Arduino")

    return {
        "success": True,
        "message": f"Direction '{cmd.direction}' sent to Arduino",
        "direction": cmd.direction,
        "command": command,
    }


@router.post("/arduino/stop")
async def stop_arduino():
    """
    Send stop command to Arduino.
    Convenience endpoint to immediately stop the rover.
    """
    if not arduino_manager.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Not connected to Arduino. Call POST /api/nav/arduino/connect first.",
        )

    success = arduino_manager.send_stop()

    if not success:
        raise HTTPException(status_code=500, detail="Failed to send stop command")

    return {"success": True, "message": "Stop command sent to Arduino"}


@router.post("/arduino/reconnect")
async def reconnect_arduino():
    """
    Attempt to reconnect to Arduino.
    Useful if connection was lost.
    """
    success = arduino_manager.reconnect()

    if not success:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to reconnect to Arduino at {arduino_manager.config.port}",
        )

    return {
        "success": True,
        "message": f"Reconnected to Arduino at {arduino_manager.config.port}",
    }
