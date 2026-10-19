"""Bounded local read caches, invalidated by input file revisions (no disk writes)."""

from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from threading import RLock
import json
import os


def file_revisions(paths):
    # On Windows directory entries carry cached stat fields. Grouping by parent
    # avoids a separate filesystem round trip for every station input.
    groups = {}
    for path in set(map(Path, paths)):
        absolute = os.path.abspath(path)
        groups.setdefault(os.path.dirname(absolute), set()).add(os.path.basename(absolute))
    revisions = []
    for parent, names in sorted(groups.items()):
        found = set()
        try:
            with os.scandir(parent) as entries:
                for entry in entries:
                    if entry.name not in names:
                        continue
                    try:
                        stat = entry.stat()
                    except FileNotFoundError:
                        continue
                    revisions.append((entry.path, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size))
                    found.add(entry.name)
        except FileNotFoundError:
            pass
        revisions.extend((os.path.join(parent, name), None, None, None) for name in names - found)
    return tuple(sorted(revisions))


class SnapshotCache:
    """LRU limited by both entries and serialized payload bytes; callers own copies."""

    def __init__(self, max_entries=8, max_bytes=8 * 1024 * 1024):
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.entries = OrderedDict()
        self.bytes = 0
        self.lock = RLock()

    def get(self, key, revision, build):
        with self.lock:
            existing = self.entries.get(key)
            if existing and existing[0] == revision:
                self.entries.move_to_end(key)
                return deepcopy(existing[1])
            value = build()
            size = len(json.dumps(value).encode('utf-8'))
            if existing:
                self.bytes -= self.entries.pop(key)[2]
            if size <= self.max_bytes:
                self.entries[key] = (revision, deepcopy(value), size)
                self.bytes += size
                while len(self.entries) > self.max_entries or self.bytes > self.max_bytes:
                    self.bytes -= self.entries.popitem(last=False)[1][2]
            return value

    def clear(self):
        with self.lock:
            self.entries.clear()
            self.bytes = 0
