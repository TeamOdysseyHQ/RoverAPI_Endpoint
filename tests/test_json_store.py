import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from app.utils.json_store import load_json, save_json, save_json_locked


class JsonStoreTests(unittest.TestCase):
    def test_concurrent_updates_preserve_every_entry(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "records.json"
            with ThreadPoolExecutor(max_workers=8) as workers:
                list(workers.map(lambda value: save_json_locked(path, lambda data: data + [value]), range(80)))
            self.assertEqual(sorted(load_json(path)), list(range(80)))

    def test_updates_are_serialized_across_processes(self):
        script = "from app.utils.json_store import save_json_locked; import sys; [save_json_locked(sys.argv[1], lambda data: data + [1]) for _ in range(15)]"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "records.json"
            processes = [subprocess.Popen([sys.executable, "-c", script, str(path)]) for _ in range(3)]
            try:
                for process in processes:
                    self.assertEqual(process.wait(timeout=15), 0)
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                        process.wait()
            self.assertEqual(len(load_json(path)), 45)

    def test_failed_serialization_preserves_the_previous_snapshot(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "records.json"
            save_json(path, ["previous"])
            with self.assertRaises(TypeError):
                save_json_locked(path, lambda data: data + [object()])
            self.assertEqual(load_json(path), ["previous"])
            self.assertEqual({p.name for p in path.parent.iterdir()}, {"records.json", "records.json.lock"})

    def test_readers_never_observe_a_partial_write(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "records.json"
            save_json(path, [])
            def read_snapshots():
                for _ in range(100):
                    self.assertIsInstance(load_json(path), list)
            with ThreadPoolExecutor(max_workers=2) as workers:
                reader = workers.submit(read_snapshots)
                for value in range(30):
                    save_json_locked(path, lambda data: data + [value])
                reader.result(timeout=5)


if __name__ == "__main__":
    unittest.main()
