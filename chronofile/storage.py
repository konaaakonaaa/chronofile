"""
Content-addressable object store.

Every version of every file's content is stored exactly once, keyed by the
SHA-1 hash of its bytes (just like a git blob). If two files -- or two
versions of the same file -- happen to have identical content, they share
storage. Content is zlib-compressed on disk.
"""

from __future__ import annotations

import hashlib
import zlib
from pathlib import Path


class ObjectStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def hash_bytes(data: bytes) -> str:
        return hashlib.sha1(data).hexdigest()

    def _path_for(self, digest: str) -> Path:
        # git-style sharding: aa/bbbbbbbb... avoids huge flat directories
        return self.root / digest[:2] / digest[2:]

    def exists(self, digest: str) -> bool:
        return self._path_for(digest).exists()

    def write(self, data: bytes) -> str:
        """Store bytes, return their content hash. No-op if already stored."""
        digest = self.hash_bytes(data)
        path = self._path_for(digest)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            compressed = zlib.compress(data, level=6)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(compressed)
            tmp.rename(path)
        return digest

    def read(self, digest: str) -> bytes:
        path = self._path_for(digest)
        if not path.exists():
            raise KeyError(f"object {digest} not found in store")
        return zlib.decompress(path.read_bytes())

    def size_on_disk(self, digest: str) -> int:
        return self._path_for(digest).stat().st_size
