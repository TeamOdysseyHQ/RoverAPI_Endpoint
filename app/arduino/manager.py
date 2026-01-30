"""Arduino serial manager for navigation commands"""

import serial
import threading
import time
from typing import Optional
from app.arduino.config import config


class ArduinoManager:
    """
    Singleton manager for Arduino serial communication.
    Handles connection lifecycle, sending commands, and reconnection.
    """

    _instance: Optional["ArduinoManager"] = None
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
        self.serial_port: Optional[serial.Serial] = None
        self.is_connected = False
        self._write_lock = threading.Lock()  # Prevent concurrent writes

    def connect(self) -> bool:
        """
        Connect to Arduino via serial port.
        Returns True if connection successful, False otherwise.
        """
        if self.serial_port and self.is_connected:
            return True

        try:
            self.serial_port = serial.Serial(
                port=self.config.port,
                baudrate=self.config.baudrate,
                timeout=self.config.timeout,
            )

            # Wait a moment for Arduino to initialize after serial connection
            time.sleep(2)

            self.is_connected = True
            print(
                f"✓ Connected to Arduino at {self.config.port} ({self.config.baudrate} baud)"
            )
            return True

        except serial.SerialException as e:
            print(f"Failed to connect to Arduino: {e}")
            self.is_connected = False
            return False
        except Exception as e:
            print(f"Unexpected error connecting to Arduino: {e}")
            self.is_connected = False
            return False

    def disconnect(self):
        """Disconnect from Arduino"""
        if self.serial_port:
            try:
                self.serial_port.close()
                self.is_connected = False
                self.serial_port = None
                print("✗ Disconnected from Arduino")
            except Exception as e:
                print(f"Error disconnecting from Arduino: {e}")

    def send_command(self, command: str) -> bool:
        """
        Send a command to Arduino.

        Args:
            command: Command string
                - Single character (W, S, A, D, X, I, J, K, L) for simple commands
                - Format "direction:speed" (e.g., "w:255") for speed-aware commands
                - Camera commands (i, j, k, l)

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.is_connected or not self.serial_port:
            print("Not connected to Arduino. Cannot send command.")
            return False

        # Parse command - check if it's a speed-aware command (direction:speed)
        if ":" in command:
            # Speed-aware command format: "w:255" or "s:120"
            parts = command.split(":")
            if len(parts) != 2:
                print(f"Invalid command format: {command}. Expected 'direction:speed'")
                return False

            direction, speed_str = parts
            direction = direction.lower()

            # Validate direction
            valid_directions = ["w", "s", "a", "d", "x"]
            if direction not in valid_directions:
                print(f"Invalid direction: {direction}. Valid: {valid_directions}")
                return False

            # Validate speed
            try:
                speed = int(speed_str)
                if speed < 0 or speed > 255:
                    print(f"Invalid speed: {speed}. Must be 0-255")
                    return False
            except ValueError:
                print(f"Invalid speed value: {speed_str}. Must be an integer")
                return False

            # Send command with speed (format: "w:255\n")
            command_bytes = f"{direction}:{speed}\n".encode()
        else:
            # Simple single character command or camera command
            cmd_lower = command.lower()
            valid_commands = ["w", "s", "a", "d", "x", "i", "j", "k", "l"]
            if cmd_lower not in valid_commands:
                print(f"Invalid command: {command}. Valid: {valid_commands}")
                return False

            # Send single character command
            command_bytes = f"{cmd_lower}\n".encode()

        try:
            with self._write_lock:
                # Send command as bytes
                self.serial_port.write(command_bytes)
                self.serial_port.flush()
                print(f"[Arduino] Sent command: {command_bytes.decode().strip()}")
                return True

        except serial.SerialException as e:
            print(f"Serial error sending command: {e}")
            self.is_connected = False
            return False
        except Exception as e:
            print(f"Failed to send command to Arduino: {e}")
            return False

    def send_stop(self) -> bool:
        """
        Send stop command to Arduino.
        Uses 'X' as stop command.

        Returns:
            True if sent successfully
        """
        return self.send_command("X")

    def get_status(self) -> dict:
        """Get connection status and info"""
        return {
            "connected": self.is_connected,
            "port": self.config.port,
            "baudrate": self.config.baudrate,
        }

    def reconnect(self) -> bool:
        """
        Attempt to reconnect to Arduino.

        Returns:
            True if reconnection successful
        """
        print("Attempting to reconnect to Arduino...")
        self.disconnect()
        time.sleep(1)
        return self.connect()


# Global instance
arduino_manager = ArduinoManager()
