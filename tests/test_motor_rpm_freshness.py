import unittest
from unittest.mock import Mock, patch

from app.ros.manager import RosbridgeManager
from app.ros.topics import MOTOR_RPM_TOPIC


class MotorRpmFreshnessTests(unittest.TestCase):
    def test_cached_reads_keep_the_same_receipt_and_identical_new_messages_advance_id(self):
        manager = object.__new__(RosbridgeManager); manager.__init__()
        manager.is_connected = True; manager.client = Mock()
        topic = Mock()
        with patch('app.ros.manager.roslibpy.Topic', return_value=topic):
            manager.subscribe_motor_rpms()
        callback = topic.subscribe.call_args.args[0]
        with patch('app.ros.manager.time.monotonic', return_value=10), patch('app.ros.manager.time.time', return_value=20):
            callback({'data': [1, 2, 3, 4, 5, 6]})
            first = manager.get_latest_motor_rpms()
        with patch('app.ros.manager.time.monotonic', return_value=13):
            cached = manager.get_latest_motor_rpms()
        self.assertEqual(first['sample_id'], cached['sample_id'])
        self.assertEqual(cached['received_at_ms'], 20000)
        self.assertEqual(cached['age_ms'], 3000)
        callback({'data': [1, 2, 3, 4, 5, 6]})
        self.assertGreater(manager.get_latest_motor_rpms()['sample_id'], first['sample_id'])
        manager.unsubscribe(MOTOR_RPM_TOPIC)
        callback({'data': [9] * 6})
        self.assertIsNone(manager.get_latest_motor_rpms())
        self.assertEqual(manager._message_metadata, {})
