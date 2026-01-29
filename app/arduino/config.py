"""Configuration for Arduino serial connection"""

import os
from typing import Optional


class ArduinoConfig:
    """Configuration for Arduino serial connection"""

    def __init__(self):
        self.port: str = os.getenv("ARDUINO_PORT", "/dev/ttyACM0")
        self.baudrate: int = int(os.getenv("ARDUINO_BAUDRATE", "9600"))
        self.timeout: float = float(os.getenv("ARDUINO_TIMEOUT", "1.0"))
        self.retry_interval: int = int(os.getenv("ARDUINO_RETRY_INTERVAL", "5"))
        self.max_retries: int = int(os.getenv("ARDUINO_MAX_RETRIES", "10"))

    def __repr__(self) -> str:
        return f"ArduinoConfig(port={self.port}, baudrate={self.baudrate})"


# Global config instance
config = ArduinoConfig()
