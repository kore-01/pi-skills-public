#!/usr/bin/env python3
"""Round-robin key pool for the Tavily skill.

A single Tavily dev key allows roughly 1,000 searches a month. This pool turns
N keys into one credential with N times the quota, and — more importantly —
lets N concurrent searches each draw a different key instead of all hammering
key 0 and tripping its rate limit.

The pointer lives in a JSON state file shared by every process, and the lease is
taken under a file lock so two threads can never receive the same credential.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:  # pragma: no cover - Windows
    try:
        import msvcrt
        _HAS_FCNTL = False
    except ImportError:
        _HAS_FCNTL = None


class KeyPoolError(RuntimeError):
    """The pool cannot serve a request (no keys, or every key is quarantined)."""


DEFAULT_KEY_FILE_LINUX = "~/.hermes/credentials/tavily-keys.txt"
DEFAULT_KEY_FILE_WINDOWS = r"D:\PI\tavily-keys.txt"
STATE_FILE_NAME = "rotation.json"


def resolve_key_file() -> Path:
    """Key file per platform: env override, then Windows path, then Linux path."""
    override = os.environ.get("TAVILY_KEY_FILE")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        return Path(DEFAULT_KEY_FILE_WINDOWS)
    return Path(DEFAULT_KEY_FILE_LINUX).expanduser()


def key_digest(key: str) -> str:
    """Short, stable id for a key. State stores digests, never plaintext."""
    return hashlib.sha256(key.strip().encode("utf-8")).hexdigest()[:12]


@dataclass
class Lease:
    index: int
    api_key: str
    digest: str


class Rotator:
    """Hands out keys strictly in file order, one per request."""

    def __init__(self, key_file: Optional[Path] = None, state_dir: Optional[Path] = None):
        self.key_file = Path(key_file) if key_file else resolve_key_file()
        self.state_dir = Path(state_dir) if state_dir else Path(__file__).resolve().parent.parent / "state"
        self.state_path = self.state_dir / STATE_FILE_NAME
        self._keys: Optional[list[str]] = None
        self._lock_path = self.state_dir / ".rotation.lock"

    # ---- key loading -------------------------------------------------

    def load_keys(self) -> list[str]:
        if self._keys is not None:
            return self._keys
        if not self.key_file.exists():
            raise KeyPoolError(f"key file not found: {self.key_file}")
        keys = []
        with self.key_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    keys.append(stripped)
        if not keys:
            raise KeyPoolError(f"no usable keys in {self.key_file}")
        self._keys = keys
        return keys

    def keys_digest(self) -> str:
        """Digest of the whole pool, so a changed pool resets the cycle."""
        keys = self.load_keys()
        joined = "\n".join(keys)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]

    # ---- state -------------------------------------------------------

    def _default_state(self) -> dict:
        return {
            "total": 0,
            "pointer": 0,
            "cycle": 1,
            "quarantine": [],
            "handed_out": 0,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            "usage": {},
            "failures": {},
            "pool_digest": self.keys_digest(),
        }

    def read_state(self) -> dict:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            return self._default_state()
        try:
            with self.state_path.open("r", encoding="utf-8") as handle:
                state = json.load(handle)
        except (json.JSONDecodeError, OSError):
            return self._default_state()
        if state.get("pool_digest") not in (None, self.keys_digest()):
            # The pool changed. The stored pointer would point into a different
            # set of keys, so start a fresh cycle.
            fresh = self._default_state()
            self.write_state(fresh)
            return fresh
        return state

    def write_state(self, state: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
        tmp = self.state_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(self.state_path)

    # ---- locking -----------------------------------------------------

    class _Lock:
        def __init__(self, path: Path):
            self.path = path
            self.handle = None

        def __enter__(self):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.handle = open(self.path, "a+")
            if _HAS_FCNTL:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
            elif _HAS_FCNTL is None and hasattr(os, "O_CREAT"):
                try:
                    import msvcrt
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
                except OSError:
                    pass
            return self

        def __exit__(self, exc_type, exc, tb):
            if self.handle is not None:
                if _HAS_FCNTL:
                    try:
                        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        pass
                self.handle.close()
                self.handle = None
            return False

    # ---- leasing -----------------------------------------------------

    def acquire(self) -> Lease:
        """Lease the next key. Raises KeyPoolError when the pool is empty."""
        keys = self.load_keys()
        with self._Lock(self._lock_path):
            state = self.read_state()
            total = len(keys)
            quarantined = set(state.get("quarantine", []))
            pointer = int(state.get("pointer", 0)) % total
            for offset in range(total):
                index = (pointer + offset) % total
                if index not in quarantined:
                    state["pointer"] = (index + 1) % total
                    state["handed_out"] = int(state.get("handed_out", 0)) + 1
                    state["total"] = total
                    self.write_state(state)
                    key = keys[index]
                    return Lease(index=index, api_key=key, digest=key_digest(key))
            raise KeyPoolError("every key in the pool is quarantined")

    def release(self, lease: Lease) -> None:
        """Return a key to the pool after a non-credential failure."""
        return None

    def quarantine(self, lease: Lease, reason: str = "") -> None:
        """Remove a key for the rest of this cycle only.

        A permanently dead key would shrink the pool forever, while a key that
        merely rate-limited rejoins at the start of the next cycle. So the
        quarantine expires with the cycle.
        """
        with self._Lock(self._lock_path):
            state = self.read_state()
            quarantined = set(state.get("quarantine", []))
            quarantined.add(lease.index)
            state["quarantine"] = sorted(quarantined)
            usage = state.setdefault("usage", {})
            usage[lease.digest] = int(usage.get(lease.digest, 0)) + 1
            failures = state.setdefault("failures", {})
            entry = failures.setdefault(lease.digest, {"count": 0, "reasons": {}})
            entry["count"] = int(entry.get("count", 0)) + 1
            entry.setdefault("reasons", {})[reason or "unknown"] = (
                int(entry.setdefault("reasons", {}).get(reason or "unknown", 0)) + 1
            )
            entry["last_at"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
            self.write_state(state)

    # ---- status -------------------------------------------------------

    def status(self) -> dict:
        keys = self.load_keys()
        state = self.read_state()
        quarantined = state.get("quarantine", [])
        failures = state.get("failures", {})
        return {
            "key_file": str(self.key_file),
            "total_keys": len(keys),
            "pointer": state.get("pointer", 0),
            "cycle": state.get("cycle", 1),
            "quarantined": len(quarantined),
            "quarantine_indices": quarantined,
            "handed_out": state.get("handed_out", 0),
            "failing_keys": len(failures),
            "available": len(keys) - len(quarantined),
            "updated_at": state.get("updated_at"),
        }

    def peek(self, count: int = 5) -> list[dict]:
        """Show the next keys without consuming quota."""
        keys = self.load_keys()
        state = self.read_state()
        pointer = int(state.get("pointer", 0)) % len(keys)
        out = []
        for offset in range(min(count, len(keys))):
            index = (pointer + offset) % len(keys)
            out.append({"index": index, "digest": key_digest(keys[index])})
        return out

    def reset(self) -> dict:
        """Clear the pointer and quarantine, starting again from key 0."""
        with self._Lock(self._lock_path):
            state = self._default_state()
            state["total"] = len(self.load_keys())
            self.write_state(state)
            return state


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Manage the Tavily key pool.")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status", help="show pool health")
    peek_cmd = sub.add_parser("next", help="preview upcoming keys")
    peek_cmd.add_argument("count", nargs="?", type=int, default=5)
    sub.add_parser("reset", help="clear pointer and quarantine")
    args = parser.parse_args(argv)

    rotator = Rotator()
    if args.command in (None, "status"):
        print(json.dumps(rotator.status(), ensure_ascii=False, indent=2))
    elif args.command == "next":
        print(json.dumps(rotator.peek(args.count), ensure_ascii=False, indent=2))
    elif args.command == "reset":
        rotator.reset()
        print("pool reset")
    return 0


if __name__ == "__main__":
    sys.exit(main())
