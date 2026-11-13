import unittest
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

from app.ros.manager import RosbridgeManager
from app.api import ros_endpoints
from fastapi import FastAPI
import httpx


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
    def test_disconnect_does_not_hold_the_topic_lock_while_waiting_for_close(self):
        manager = object.__new__(RosbridgeManager); manager.__init__()
        manager.is_connected = True
        entered = threading.Event()
        manager.client = Mock(is_connected=True)
        manager.client.close.side_effect = entered.set
        with ThreadPoolExecutor(max_workers=2) as workers:
            closing = workers.submit(manager.disconnect)
            try:
                self.assertTrue(entered.wait(1))
                status = workers.submit(manager.get_status).result(timeout=.3)
                self.assertFalse(status['connected'])
                self.assertFalse(closing.done())
            finally:
                manager._closed.set(); closing.result(timeout=2)
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


class RosStatusConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_waiting_ros_status_read_does_not_block_api_health(self):
        manager = object.__new__(RosbridgeManager); manager.__init__()
        entered, release = threading.Event(), threading.Event()
        def hold_topic_lock():
            with manager._topic_lock:
                entered.set(); release.wait(2)
        holding = asyncio.create_task(asyncio.to_thread(hold_topic_lock))
        self.assertTrue(await asyncio.to_thread(entered.wait, 1))
        app = FastAPI(); app.include_router(ros_endpoints.router)
        with patch.object(ros_endpoints, 'ros_manager', manager):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                reading = asyncio.create_task(client.get('/ros/status'))
                try:
                    await asyncio.sleep(.02)
                    self.assertEqual((await asyncio.wait_for(client.get('/status'), .3)).status_code, 200)
                    self.assertFalse(reading.done())
                finally:
                    release.set(); await holding; await reading


if __name__ == "__main__":
    unittest.main()
