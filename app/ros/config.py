"""Configuration for ROS bridge connection"""

import os
from typing import Optional


class RosbridgeConfig:
    """Configuration for rosbridge WebSocket connection"""

    def __init__(self):
        self.host: str = os.getenv("ROSBRIDGE_HOST", "localhost")
        self.port: int = int(os.getenv("ROSBRIDGE_PORT", "9090"))
        self.retry_interval: int = int(os.getenv("ROSBRIDGE_RETRY_INTERVAL", "5"))
        self.max_retries: int = int(os.getenv("ROSBRIDGE_MAX_RETRIES", "10"))

    @property
    def url(self) -> str:
        """Get the WebSocket URL"""
        return f"ws://{self.host}:{self.port}"

    def __repr__(self) -> str:
        return f"RosbridgeConfig(host={self.host}, port={self.port})"


# Global config instance
config = RosbridgeConfig()
