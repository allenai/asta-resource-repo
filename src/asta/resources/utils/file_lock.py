"""Cross-platform advisory locking on open file handles

Uses ``fcntl.flock`` on POSIX and ``msvcrt.locking`` on Windows. Windows has no
shared locks, so ``shared=True`` falls back to an exclusive lock there.
"""

from contextlib import contextmanager
from typing import IO, Iterator
import os

if os.name == "nt":
    import msvcrt

    @contextmanager
    def locked(f: IO, shared: bool = False) -> Iterator[None]:
        """Hold a lock on ``f`` for the duration of the block"""
        # msvcrt locks a byte range starting at the current position; lock the
        # first byte (valid even past EOF) and restore the position afterwards.
        pos = f.tell()
        f.seek(0)
        # LK_LOCK retries for ~10 seconds before raising OSError
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        f.seek(pos)
        try:
            yield
        finally:
            f.flush()
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    @contextmanager
    def locked(f: IO, shared: bool = False) -> Iterator[None]:
        """Hold a lock on ``f`` for the duration of the block"""
        fcntl.flock(f.fileno(), fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
