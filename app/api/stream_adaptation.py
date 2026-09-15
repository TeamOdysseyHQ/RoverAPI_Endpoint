"""Per-viewer spatial adaptation; codec bitrate remains controlled by RTCP REMB.

No global encoder mutation, camera restart, or frame-rate reduction is used.
The thresholds are conservative defaults, not hardware performance guarantees.
"""

import math


class AdaptiveQuality:
    SCALES = (1.0, 0.85, 0.7, 0.5)

    def __init__(self, target_fps):
        self.target_fps = max(1, min(60, float(target_fps)))
        self.level = 0
        self.bad_samples = 0
        self.good_samples = 0

    @property
    def scale(self):
        return self.SCALES[self.level]

    def update(self, feedback):
        fields = ("received_fps", "loss_ratio", "jitter_ms", "decode_ms")
        values = [float(feedback.get(key, 0)) for key in fields]
        if not all(math.isfinite(value) and value >= 0 for value in values):
            raise ValueError("Feedback must contain finite, nonnegative values")
        fps, loss, jitter, decode = values
        if loss > 1:
            raise ValueError("Loss ratio must be between zero and one")
        budget = 1000 / self.target_fps
        bad = fps < self.target_fps * 0.8 or loss > 0.03 or jitter > 40 or decode > budget * 0.8
        good = fps >= self.target_fps * 0.9 and loss < 0.01 and jitter < 20 and decode < budget * 0.6
        self.bad_samples = self.bad_samples + 1 if bad else 0
        self.good_samples = self.good_samples + 1 if good else 0
        if self.bad_samples >= 2:
            self.level = min(len(self.SCALES) - 1, self.level + 1)
            self.bad_samples = self.good_samples = 0
        elif self.good_samples >= 5:
            self.level = max(0, self.level - 1)
            self.bad_samples = self.good_samples = 0
        return {"target_fps": self.target_fps, "scale": self.scale, "bitrate_control": "rtcp-remb"}


class FramePacer:
    """Monotonic RTP clock with no burst to catch up after a slow frame."""

    def __init__(self, fps):
        self.interval = 1 / max(1, min(60, float(fps)))
        self.started = None
        self.next_due = None

    def delay(self, now):
        return max(0, self.next_due - now) if self.next_due is not None else 0

    def timestamp(self, now):
        if self.started is None:
            self.started = now
        self.next_due = now + self.interval
        return round((now - self.started) * 90000)
