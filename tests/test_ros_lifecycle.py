import unittest
from unittest.mock import patch

from app.ros.manager import RosbridgeManager


class Client:
    def __init__(self, **kwargs):
        self.callbacks = {}
        self.is_connected = False
        self.scheduled = 0

    def on(self, event, callback):
        self.callbacks[event] = callback

    def on_ready(self, callback):
        self.on("ready", lambda _: callback())

    def connect(self):
        self.is_connected = True
        self.callbacks["ready"](self)

    def run(self):
        if not self.is_connected:
            self.connect()

    def call_later(self, delay, callback):
        self.scheduled += 1
        callback()

    def close(self):
        self.is_connected = False
        self.callbacks["close"](self)


class RosLifecycleTests(unittest.TestCase):
    def test_reconnect_reuses_client_and_callbacks_accept_protocol_argument(self):
        manager = object.__new__(RosbridgeManager)
        manager.__init__()
        with patch("app.ros.manager.roslibpy.Ros", side_effect=Client) as create:
            for _ in range(3):
                self.assertTrue(manager.connect())
                self.assertTrue(manager.is_connected)
                manager.disconnect()
                self.assertFalse(manager.is_connected)
            self.assertEqual(create.call_count, 1)
            self.assertEqual(manager.client.scheduled, 2)

    def test_automatic_reconnect_updates_the_manager_after_a_close(self):
        manager = object.__new__(RosbridgeManager)
        manager.__init__()
        with patch("app.ros.manager.roslibpy.Ros", side_effect=Client):
            self.assertTrue(manager.connect())
            manager.client.close()
            self.assertFalse(manager.is_connected)
            manager.client.connect()
            self.assertTrue(manager.is_connected)


if __name__ == "__main__":
    unittest.main()
