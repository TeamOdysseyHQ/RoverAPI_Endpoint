"""JSON snapshots with serialized updates across threads and processes."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import threading

if os.name == "nt":
    import msvcrt
else:
    import fcntl

_locks = {}
_locks_guard = threading.Lock()


@contextmanager
def _locked(path):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _locks_guard:
        lock = _locks.setdefault(path, threading.RLock())
    with lock, open(str(path) + ".lock", "a+b") as handle:
        if os.name == "nt":
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield path
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def load_json(path):
    # Windows cannot replace a file while a reader holds its handle open.
    if os.name == "nt":
        with _locked(path) as target:
            return _load_json(target)
    return _load_json(path)


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return []


def _write_json(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         delete=False) as handle:
            temporary = handle.name
            json.dump(data, handle, separators=(",", ":"))
        # Readers see a complete old or new snapshot, never a truncated file.
        os.replace(temporary, path)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def save_json(path, data):
    with _locked(path) as target:
        _write_json(target, data)


def save_json_locked(path, updater):
    with _locked(path) as target:
        data = updater(_load_json(target))
        _write_json(target, data)
        return data
