"""Exercise native-source reservations and viewer ownership without camera hardware."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch
from app.api import webrtc_utils as rtc


class Source:
    fps = 60
    def __init__(self):
        self.peers = set()
        self.fail = False
        self.stopped = False
    def status(self):
        return {'active':not self.stopped, 'peers':list(self.peers), 'fps':60}
    def request(self, cmd, **values):
        peer_id = values.get('peer_id')
        if cmd == 'offer':
            self.peers.add(peer_id)
            if self.fail:
                raise RuntimeError('Invalid native SDP')
            return {'sdp':'answer', 'type':'answer'}
        if cmd == 'close':
            found = peer_id in self.peers
            self.peers.discard(peer_id)
            return {'closed':found}
        if cmd == 'timing':return {'frames':[]}
    def stop(self):self.stopped = True


class MdnsCandidateTests(unittest.TestCase):
    def test_mdns_uses_validated_api_address_and_preserves_numeric_candidates(self):
        offer = ('a=ice-pwd:unchanged\r\n'
                 'a=candidate:0 1 UDP 2122252543 browser.LOCAL. 49152 typ host\r\n'
                 'a=candidate:1 1 udp 123 192.168.1.80 5000 typ host\r\n'
                 'a=candidate:2 1 udp 456 203.0.113.8 6000 typ srflx raddr 192.168.1.80 rport 5000\r\n')
        for host in ['192.168.1.159', '2001:db8::1234']:
            with self.subTest(host=host):
                self.assertEqual(rtc._mdns_candidates_for_peer(offer, host),
                                 offer.replace('browser.LOCAL.', host))

    def test_missing_or_non_numeric_api_address_leaves_offer_unchanged(self):
        offer = 'a=candidate:0 1 UDP 123 browser.local 49152 typ host\r\n'
        for host in [None, 'proxy.local', 'not an IP']:
            with self.subTest(host=host):
                self.assertEqual(rtc._mdns_candidates_for_peer(offer, host), offer)


class WebRTCLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        rtc._peer_connections.clear(); rtc._sources.clear(); rtc._pending_peers.clear(); rtc._owned_ros_topics.clear()
        rtc._pc_lock = asyncio.Lock()
        rtc._ros_locks.clear()
        self.source = Source()
        self.patcher = patch.object(rtc, '_hardware_source', return_value=self.source)
        self.patcher.start()
        self.ros = Mock(_subscribers={})
        self.ros.subscribe_camera_image.return_value = True
        self.ros_patcher = patch.object(rtc, 'ros_manager', self.ros)
        self.ros_patcher.start()
    async def asyncTearDown(self):
        for name in list(rtc._peer_connections):await rtc.close_all_connections(name)
        if rtc._source_reaper:
            task = rtc._source_reaper
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.patcher.stop()
        self.ros_patcher.stop()

    async def test_ros_subscription_is_released_only_after_the_last_viewer(self):
        frame = Mock(shape=(240, 320, 3))
        with patch.object(rtc, '_start_ros_source', new=AsyncMock(return_value=self.source)):
            a = await rtc.handle_offer('ros_camera:/image', 'offer', 'offer', lambda: frame)
            b = await rtc.handle_offer('ros_camera:/image', 'offer', 'offer', lambda: frame)
        self.ros.subscribe_camera_image.assert_called_once_with('/image')
        await rtc.close_peer_connection('ros_camera:/image', a['peer_id'])
        self.ros.unsubscribe.assert_not_called()
        await rtc.close_peer_connection('ros_camera:/image', b['peer_id'])
        self.assertTrue(self.source.stopped)
        self.ros.unsubscribe.assert_called_once_with('/image')

    async def test_slow_status_cannot_block_an_unrelated_peer_close(self):
        a = await self.offer()
        entered, release = threading.Event(), threading.Event()
        other = Source()
        with patch.object(rtc, '_hardware_source', return_value=other):
            b = await self.offer('camera:other')
        original = self.source.status
        def slow_status():
            entered.set(); release.wait(2); return original()
        with patch.object(self.source, 'status', side_effect=slow_status):
            reading = asyncio.create_task(rtc.get_connection_count('camera:kreo'))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                self.assertTrue(await asyncio.wait_for(rtc.close_peer_connection('camera:other', b['peer_id']), .3))
            finally:
                release.set(); await reading
        self.assertEqual(self.source.peers, {a['peer_id']})

    async def test_status_snapshot_cannot_prune_a_peer_created_while_it_waits(self):
        await self.offer()
        entered, release = threading.Event(), threading.Event()
        original = self.source.status
        def slow_snapshot():
            status = original(); entered.set(); release.wait(2); return status
        with patch.object(self.source, 'status', side_effect=slow_snapshot):
            reading = asyncio.create_task(rtc.get_connection_count('camera:kreo'))
            self.assertTrue(await asyncio.to_thread(entered.wait, 1))
            # Reserve through the real entry point while the first status is in flight.
            with patch.object(self.source, 'status', side_effect=original):
                b = await self.offer()
            release.set(); await reading
        self.assertIn(b['peer_id'], rtc._peer_connections['camera:kreo'])

    async def test_slow_ros_shutdown_does_not_block_an_unrelated_offer(self):
        frame = Mock(shape=(240, 320, 3))
        with patch.object(rtc, '_start_ros_source', new=AsyncMock(return_value=self.source)):
            a = await rtc.handle_offer('ros_camera:/image', 'offer', 'offer', lambda: frame)
        entered, release = threading.Event(), threading.Event()
        def slow_stop(): entered.set(); release.wait(2)
        with patch.object(self.source, 'stop', side_effect=slow_stop):
            closing = asyncio.create_task(rtc.close_peer_connection('ros_camera:/image', a['peer_id']))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                with patch.object(rtc, '_hardware_source', return_value=Source()):
                    await asyncio.wait_for(self.offer('camera:other'), .3)
            finally:
                release.set(); await closing

    async def test_existing_explicit_ros_subscription_outlives_video(self):
        self.ros._subscribers['/image'] = object()
        with patch.object(rtc, '_start_ros_source', new=AsyncMock(return_value=self.source)):
            a = await rtc.handle_offer('ros_camera:/image', 'offer', 'offer', lambda: Mock(shape=(240, 320, 3)))
        await rtc.close_peer_connection('ros_camera:/image', a['peer_id'])
        self.ros.subscribe_camera_image.assert_not_called()
        self.ros.unsubscribe.assert_not_called()

    async def test_explicit_subscription_added_during_video_is_preserved(self):
        with patch.object(rtc, '_start_ros_source', new=AsyncMock(return_value=self.source)):
            a = await rtc.handle_offer('ros_camera:/image', 'offer', 'offer', lambda: Mock(shape=(240, 320, 3)))
        self.assertTrue(await rtc.subscribe_ros_camera('/image'))
        await rtc.close_peer_connection('ros_camera:/image', a['peer_id'])
        self.ros.unsubscribe.assert_not_called()

    async def test_failed_ros_encoder_start_releases_its_subscription(self):
        with patch.object(rtc, '_start_ros_source', new=AsyncMock(side_effect=RuntimeError('encoder failed'))):
            with self.assertRaisesRegex(RuntimeError, 'encoder failed'):
                await rtc.handle_offer('ros_camera:/image', 'offer', 'offer', lambda: Mock(shape=(240, 320, 3)))
        self.ros.unsubscribe.assert_called_once_with('/image')
        self.assertEqual(rtc._owned_ros_topics, set())

    async def test_cancelled_subscription_waits_for_completion_before_unsubscribing(self):
        entered, release = threading.Event(), threading.Event()
        def subscribe(_topic):
            entered.set()
            release.wait(2)
            return True
        self.ros.subscribe_camera_image.side_effect = subscribe
        starting = asyncio.create_task(rtc.handle_offer('ros_camera:/image', 'offer', 'offer', lambda: None))
        self.assertTrue(await asyncio.to_thread(entered.wait, 1))
        starting.cancel()
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await starting
        self.ros.unsubscribe.assert_called_once_with('/image')
        self.assertEqual(rtc._owned_ros_topics, set())
    async def offer(self, name='camera:kreo'):
        return await rtc.handle_offer(name, 'offer', 'offer')
    async def test_one_viewer_closes_without_stopping_shared_encoder(self):
        a,b = await asyncio.gather(self.offer(),self.offer())
        self.assertIsNotNone(rtc._source_reaper)
        self.assertEqual(a['target_fps'],60)
        self.assertEqual(a['codec'],'H264')
        self.assertFalse(a['adaptive_quality'])
        self.assertTrue(await rtc.close_peer_connection('camera:kreo',a['peer_id']))
        self.assertEqual(self.source.peers,{b['peer_id']})
        self.assertFalse(self.source.stopped)
    async def test_peer_cannot_close_another_source_and_repeated_close_is_safe(self):
        a = await self.offer()
        self.assertFalse(await rtc.close_peer_connection('microscope',a['peer_id']))
        self.assertEqual(await rtc.get_connection_count('camera:kreo'),1)
        self.assertTrue(await rtc.close_peer_connection('camera:kreo',a['peer_id']))
        self.assertFalse(await rtc.close_peer_connection('camera:kreo',a['peer_id']))
    async def test_capacity_is_atomic_across_device_aliases(self):
        results = await asyncio.gather(*(self.offer('camera:kreo' if i%2 else 'camera:video2') for i in range(12)),return_exceptions=True)
        self.assertEqual(sum(isinstance(r,dict) for r in results),5)
        self.assertTrue(all(isinstance(r,(dict,ValueError)) for r in results))
        self.assertEqual(len(self.source.peers),5)
    async def test_failed_negotiation_reclaims_registration_and_native_peer(self):
        self.source.fail = True
        with self.assertRaisesRegex(RuntimeError,'Invalid native SDP'):await self.offer()
        self.assertEqual(self.source.peers,set())
        self.assertEqual(rtc._peer_connections,{})
        self.assertEqual(rtc._pending_peers,set())
    async def test_transport_failure_releases_capacity_on_next_status(self):
        await self.offer()
        self.source.peers.clear()
        self.assertEqual(await rtc.get_connection_count('camera:kreo'),0)
        self.assertEqual(rtc._peer_connections,{})
        self.assertIsInstance(await self.offer(),dict)
    async def test_close_all_leaves_other_physical_source_running(self):
        await self.offer();await self.offer()
        other = Source()
        with patch.object(rtc,'_hardware_source',return_value=other):
            second = await self.offer('camera:arm')
        self.assertEqual(await rtc.close_all_connections('camera:kreo'),2)
        self.assertEqual(other.peers,{second['peer_id']})

    async def test_cancelled_ros_constructor_stops_its_late_source(self):
        entered, release = threading.Event(), threading.Event()
        def construct(*args):
            entered.set()
            release.wait(2)
            return self.source
        with patch.object(rtc, 'GStreamerSource', side_effect=construct):
            starting = asyncio.create_task(rtc._start_ros_source(lambda: None, 320, 240, 30))
            self.assertTrue(await asyncio.to_thread(entered.wait, 1))
            starting.cancel()
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await starting
        self.assertTrue(self.source.stopped)
        self.assertEqual(rtc._sources, {})

    async def test_cancel_before_reservation_still_reclaims_registered_ros_source(self):
        entered, never, allow_reap = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def prune(source):
            if not entered.is_set():
                entered.set()
                await never.wait()
            return set()
        async def wait_for_reap(_delay):
            await allow_reap.wait()
        frame = Mock(shape=(240, 320, 3))
        with patch.dict(rtc.ros_manager._subscribers, {'test': Mock()}), patch.object(rtc, '_start_ros_source', new=AsyncMock(return_value=self.source)), patch.object(rtc, '_prune', side_effect=prune), patch.object(rtc.asyncio, 'sleep', side_effect=wait_for_reap):
            starting = asyncio.create_task(rtc.handle_offer('ros_camera:test', 'offer', 'offer', lambda: frame))
            await asyncio.wait_for(entered.wait(), 2)
            starting.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await starting
            self.assertIsNotNone(rtc._source_reaper)
            allow_reap.set()
            await asyncio.wait_for(rtc._source_reaper, 2)
        self.assertTrue(self.source.stopped)
        self.assertEqual(rtc._sources, {})

    async def test_abandoned_ros_source_is_reclaimed_without_status_requests(self):
        rtc._sources['ros_camera:test'] = self.source
        rtc._peer_connections['ros_camera:test'] = {'gone': self.source}
        with patch.object(rtc.asyncio, 'sleep', new=AsyncMock()):
            await rtc._reap_sources()
        self.assertTrue(self.source.stopped)
        self.assertEqual(rtc._sources, {})
        self.assertEqual(rtc._peer_connections, {})


class NativeCameraOwnershipTests(unittest.TestCase):
    def test_concurrent_alias_starts_share_one_encoder_and_stop_releases_all_aliases(self):
        from app.api.navigation.camera import MultiCameraManager
        manager = MultiCameraManager()
        source = Mock(width=1280, height=720, fps=60)
        source.status.return_value = {'active':True, 'peers':[], 'fps':60}
        with patch.object(manager, '_device_path', return_value='/dev/video2'), patch('os.path.exists', return_value=True), patch('app.media.gstreamer.GStreamerSource', return_value=source) as create:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda n: manager.start_camera(n, 1280, 720, 60, 'MJPG'), ['kreo','video2']*4))
            self.assertTrue(all(results))
            create.assert_called_once()
            self.assertIs(manager.cameras['kreo'], manager.cameras['video2'])
            self.assertTrue(manager.stop_camera('kreo'))
            source.stop.assert_called_once()
            self.assertEqual(manager.cameras, {})

    def test_mode_conflict_preserves_existing_viewers(self):
        from app.api.navigation.camera import MultiCameraManager
        from fastapi import HTTPException
        manager = MultiCameraManager()
        source = Mock(width=1280, height=720, fps=60)
        source.status.return_value = {'active':True}
        manager.cameras['kreo'] = source
        manager.camera_info['kreo'] = {'device_path':'/dev/video2'}
        with patch.object(manager, '_device_path', return_value='/dev/video2'), patch('os.path.exists', return_value=True):
            with self.assertRaises(HTTPException) as conflict:
                manager.start_camera('video2', 640, 480, 30)
            self.assertEqual(conflict.exception.status_code, 409)
            source.stop.assert_not_called()
