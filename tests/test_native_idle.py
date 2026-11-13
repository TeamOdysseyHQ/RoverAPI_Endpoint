"""Exercise the worker's idle snapshot path without a physical V4L2 camera."""
import ast
import base64
from collections import deque
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class IdleSnapshotTests(unittest.TestCase):
    def test_idle_snapshot_waits_for_a_new_buffer_and_wakes_only_once(self):
        path = Path(__file__).resolve().parents[1] / 'app/media/gst_worker.py'
        tree = ast.parse(path.read_text())
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ('reap', 'command', 'save_jpeg', 'finish_captures')]
        callbacks = []
        pipeline, reply = Mock(), Mock()
        gst = SimpleNamespace(State=SimpleNamespace(PAUSED='paused', PLAYING='playing'), FlowReturn=SimpleNamespace(OK='ok'))
        scope = dict(Gst=gst, GLib=SimpleNamespace(idle_add=lambda fn: callbacks.append(fn)),
                     GstWebRTC=Mock(), time=SimpleNamespace(monotonic=lambda: 20),
                     pipeline=pipeline, reply=reply, base64=base64, peers={},
                     captured=deque([1, 2]), idle=False, idle_since=0,
                     capture_waiters={}, latest_jpeg=b'old', latest_raw=None)
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), scope)
        scope['reap']()
        pipeline.set_state.assert_called_once_with('paused')
        self.assertFalse(scope['captured'])
        scope['command']({'cmd': 'capture', 'id': 'a'})
        scope['command']({'cmd': 'capture', 'id': 'b'})
        self.assertEqual(pipeline.set_state.call_count, 2)
        pipeline.set_state.assert_called_with('playing')
        reply.assert_not_called()
        buffer = Mock()
        buffer.extract_dup.return_value = b'fresh'
        sink = Mock()
        sink.emit.return_value.get_buffer.return_value = buffer
        scope['save_jpeg'](sink)
        callbacks.pop()()
        self.assertEqual({call.args[0] for call in reply.call_args_list}, {'a', 'b'})
        self.assertTrue(all(base64.b64decode(call.kwargs['jpeg']) == b'fresh' for call in reply.call_args_list))
