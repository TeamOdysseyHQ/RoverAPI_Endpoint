import asyncio
import unittest
from unittest.mock import Mock, patch

from app.api.science import drill_data


class ScienceTelemetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_telemetry_returns_without_sleeping_and_subscribes_once(self):
        manager = Mock(is_connected=True, _subscribers={})
        manager.get_latest_drill_data.return_value = None
        manager.get_latest_science_warning.return_value = None
        manager.subscribe_drill_data.side_effect = lambda: manager._subscribers.setdefault(drill_data.SCIENCE_DRILL_DATA_TOPIC, True)
        manager.subscribe_science_warnings.side_effect = lambda: manager._subscribers.setdefault(drill_data.SCIENCE_INFO_WARNING_TOPIC, True)
        with patch.object(drill_data, 'ros_manager', manager), patch('time.sleep', side_effect=AssertionError('Telemetry reads must not block')):
            for _ in range(2):
                drill, warning = await asyncio.gather(drill_data.get_drill_data(), drill_data.get_latest_warning())
                self.assertFalse(drill['success'])
                self.assertIsNone(drill['data'])
                self.assertIsNone(warning['data']['warning_code'])
        manager.subscribe_drill_data.assert_called_once()
        manager.subscribe_science_warnings.assert_called_once()

    async def test_cached_measurements_are_returned_unchanged(self):
        manager = Mock(is_connected=True, _subscribers={drill_data.SCIENCE_DRILL_DATA_TOPIC: True, drill_data.SCIENCE_INFO_WARNING_TOPIC: True})
        manager.get_latest_drill_data.return_value = {'distance_mm': 42, 'drill_halted': True}
        manager.get_latest_science_warning.return_value = 2
        with patch.object(drill_data, 'ros_manager', manager):
            self.assertEqual((await drill_data.get_drill_data())['data'], manager.get_latest_drill_data.return_value)
            self.assertEqual((await drill_data.get_latest_warning())['data']['warning_code'], 2)
