"""Shared expedition locations for captures and reports."""

from datetime import datetime
import os
from pathlib import Path
import re
from uuid import uuid4

from fastapi import HTTPException

EXPEDITION_BASE_DIR = os.environ.get(
    "EXPEDITION_BASE_DIR", "/home/administratror/expeditions/unprocessed"
)
EXPEDITION_PROCESSED_DIR = os.environ.get(
    "EXPEDITION_PROCESSED_DIR", str(Path(EXPEDITION_BASE_DIR).parent / "processed")
)


def expedition_path(expedition_id, processed=False):
    if (not isinstance(expedition_id, str) or not expedition_id
            or expedition_id in (".", "..")
            or not re.fullmatch(r"[\w.-]+", expedition_id)):
        raise HTTPException(status_code=400, detail="Invalid expedition ID.")
    base = Path(EXPEDITION_PROCESSED_DIR if processed else EXPEDITION_BASE_DIR).resolve()
    target = (base / expedition_id).resolve()
    if base not in target.parents:
        raise HTTPException(status_code=400, detail="Invalid expedition ID.")
    return str(target)


def get_safe_expedition_dir(expedition_id):
    target = expedition_path(expedition_id)
    os.makedirs(target, exist_ok=True)
    return target


def create_expedition():
    Path(EXPEDITION_BASE_DIR).mkdir(parents=True, exist_ok=True)
    while True:
        expedition_id = uuid4().hex
        try:
            Path(expedition_path(expedition_id)).mkdir()
            return expedition_id
        except FileExistsError:
            continue


def capture_details(filename):
    """Recognize dated captures with/without microseconds and legacy epoch names."""
    match = re.fullmatch(r"(\d{8}_\d{6})(?:_(\d{6}))?_(.+)_capture\.[^.]+", filename)
    if match:
        stamp = match[1] + ("_" + match[2] if match[2] else "")
        fmt = "%Y%m%d_%H%M%S_%f" if match[2] else "%Y%m%d_%H%M%S"
        try:
            return match[3], datetime.strptime(stamp, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return match[3], "Unknown"
    match = re.fullmatch(r"(\d+)_(\d+)_(.+)_capture\.[^.]+", filename)
    if match:
        try:
            return match[3], datetime.fromtimestamp(float(f"{match[1]}.{match[2]}")).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OverflowError, OSError):
            pass
    return "unknown", "Unknown"
