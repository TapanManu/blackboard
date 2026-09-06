"""Content-addressed artifact store (Delta6).

sha256 keys give free dedup across agents, integrity verification, and
immutability: a URI in an old spec can never silently change underneath a reader.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import threading
from pathlib import Path
from typing import Optional, Protocol

from .uri import artifact_uri, parse_artifact

THRESHOLD_BYTES = 10 * 1024        # matches the original blueprint's 10 KB


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class Artifacts(Protocol):
    def put(self, data: bytes) -> str: ...
    def get(self, uri: str) -> Optional[bytes]: ...
    def exists(self, uri: str) -> bool: ...
    def size(self, uri: str) -> Optional[int]: ...


class LocalArtifacts:
    """Fan-out by first two hex chars, so a directory never holds 100k files."""

    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    def _path(self, hex_: str) -> Path:
        return self.root / hex_[:2] / hex_

    def put(self, data: bytes) -> str:
        hex_ = sha256_bytes(data)
        p = self._path(hex_)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            # Temp name must be unique PER WRITER: concurrent writers of identical
            # content would otherwise race on one .tmp path and rename a vanished file.
            tmp = p.with_name(f"{hex_}.{os.getpid()}.{threading.get_ident()}."
                              f"{secrets.token_hex(4)}.tmp")
            try:
                tmp.write_bytes(data)
                os.chmod(tmp, 0o600)
                os.replace(tmp, p)             # atomic; concurrent writers converge
            finally:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
        return artifact_uri(hex_)

    def put_file(self, path: str) -> tuple:
        """Server-side ingestion (Delta12): bulk content never enters a context window."""
        data = Path(path).read_bytes()
        return self.put(data), len(data)

    def get(self, uri: str) -> Optional[bytes]:
        p = self._path(parse_artifact(uri))
        if not p.exists():
            return None
        data = p.read_bytes()
        if sha256_bytes(data) != parse_artifact(uri):
            from .errors import PayloadError
            raise PayloadError("artifact hash mismatch; store is corrupt", uri=uri)
        return data

    def exists(self, uri: str) -> bool:
        return self._path(parse_artifact(uri)).exists()

    def size(self, uri: str) -> Optional[int]:
        p = self._path(parse_artifact(uri))
        return p.stat().st_size if p.exists() else None
