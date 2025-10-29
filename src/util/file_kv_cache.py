"""FileKVCache: tiny append-only JSONL cache.

- Backed by a single JSONL file for durability and easy inspection.
- Get semantics: return the value if present; otherwise return False (per user request).
- Put semantics: append a new record immediately and fsync to avoid losing work.
- Maintains an in-memory index (key -> last value) rebuilt on start.

Each line in the file is a JSON object: {"key": <key>, "value": <value>, "ts": "<iso8601>"}
You can store any JSON-serializable "value".

Example:
    cache = FileKVCache("cache/results.jsonl")
    v = cache.get("some-key")  # returns value or False
    if v is False:
        v = heavy_compute()
        cache.set("some-key", v)  # appended + flushed immediately
"""

from __future__ import annotations
import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import os
import json
from datetime import datetime

@dataclass
class FileKVCache:
    path: Path

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        self._index: Dict[str, Any] = {}
        self._build_index()

    def get(self, key: str) -> Any | bool:
        """Return cached value for 'key' if present; else return False."""
        return self._index.get(key, False)

    def get_or_false(self, key: str) -> Any | bool:
        return self.get(key)

    def get_or_call(self, key: str, fn: functools.partial, kwargs: dict) -> Any:
        """Return cached value for 'key' if present; else call fn(), cache, and return."""
        v = self.get(key)
        if v is not False:
            return v
        v = fn(**kwargs)
        self.set(key, v)
        return v

    def has(self, key: str) -> bool:
        return key in self._index

    def set(self, key: str, value: Any) -> None:
        """Append {key,value,ts} to the JSONL file, fsync, and update index."""
        rec = {
            "key": key,
            "value": value,
            "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        line = json.dumps(rec, ensure_ascii=False)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        self._index[key] = value

    def keys(self):
        return list(self._index.keys())

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._index)

    def _build_index(self) -> None:
        self._index.clear()
        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    k = obj.get("key", None)
                    if k is None:
                        continue
                    self._index[k] = obj.get("value", None)
                except json.JSONDecodeError:
                    continue
