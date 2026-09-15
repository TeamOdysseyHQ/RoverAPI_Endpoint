import unittest
from app.api.stream_adaptation import AdaptiveQuality, FramePacer


class StreamAdaptationTests(unittest.TestCase):
    def feedback(self, fps=60, loss=0, jitter=0, decode=1):
        return dict(received_fps=fps, loss_ratio=loss, jitter_ms=jitter, decode_ms=decode)

    def test_quality_drops_before_fps_and_recovers_with_hysteresis(self):
        quality = AdaptiveQuality(60)
        self.assertEqual(quality.update(self.feedback(loss=0.1))["scale"], 1)
        self.assertEqual(quality.update(self.feedback(loss=0.1))["scale"], 0.85)
        self.assertEqual(quality.target_fps, 60)
        for _ in range(4):
            self.assertEqual(quality.update(self.feedback())["scale"], 0.85)
        self.assertEqual(quality.update(self.feedback())["scale"], 1)

    def test_profiles_are_independent_and_bounded(self):
        slow, healthy = AdaptiveQuality(15), AdaptiveQuality(60)
        for _ in range(30):
            slow.update(self.feedback(fps=0))
        self.assertEqual(slow.scale, 0.5)
        self.assertEqual(slow.target_fps, 15)
        self.assertEqual(healthy.scale, 1)

    def test_invalid_feedback_is_rejected(self):
        for value in (float("nan"), float("inf"), -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                AdaptiveQuality(30).update(self.feedback(jitter=value))

    def test_60fps_pacing_uses_1500_tick_steps_not_fixed_30fps(self):
        pacer = FramePacer(60)
        self.assertEqual(pacer.timestamp(100), 0)
        self.assertAlmostEqual(pacer.delay(100), 1 / 60)
        self.assertEqual(pacer.timestamp(100 + 1 / 60), 1500)

    def test_24fps_target_uses_3750_tick_steps(self):
        pacer = FramePacer(24)
        self.assertEqual(pacer.timestamp(100), 0)
        self.assertAlmostEqual(pacer.delay(100), 1 / 24)
        self.assertEqual(pacer.timestamp(100 + 1 / 24), 3750)

    def test_slow_capture_does_not_produce_catchup_bursts(self):
        pacer = FramePacer(30)
        pacer.timestamp(100)
        self.assertEqual(pacer.delay(101), 0)
        self.assertEqual(pacer.timestamp(101), 90000)
        self.assertAlmostEqual(pacer.delay(101), 1 / 30)


if __name__ == "__main__":
    unittest.main()
