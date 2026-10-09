"""Decode sensor_msgs/Image, including padded rows and rosbridge byte arrays."""

import base64
import cv2
import numpy as np


def decode_ros_image(message):
    width, height = message.get("width", 0), message.get("height", 0)
    encoding = message.get("encoding", "rgb8")
    channels = {"rgb8": 3, "bgr8": 3, "mono8": 1}.get(encoding)
    if not channels or not isinstance(width, int) or not isinstance(height, int) or min(width, height) <= 0:
        return None
    step = message.get("step", width * channels)
    if not isinstance(step, int) or step < width * channels:
        return None
    try:
        data = message.get("data", "")
        raw = base64.b64decode(data, validate=True) if isinstance(data, str) else bytes(data)
        if len(raw) < height * step:
            return None
        rows = np.frombuffer(raw, dtype=np.uint8, count=height * step).reshape(height, step)
        pixels = rows[:, :width * channels].reshape(height, width, channels)
        if encoding == "mono8":
            return cv2.cvtColor(pixels, cv2.COLOR_GRAY2BGR)
        if encoding == "rgb8":
            pixels = pixels[:, :, ::-1]
        return np.ascontiguousarray(pixels)
    except (ValueError, TypeError, OverflowError):
        return None


def encode_ros_jpeg(message, quality):
    frame = decode_ros_image(message)
    if frame is None:
        return None
    ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buffer.tobytes() if ok else None
