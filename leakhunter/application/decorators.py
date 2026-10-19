"""Cross-cutting application decorators."""
from __future__ import annotations

from functools import wraps
from threading import Lock


def exclusive(lock: Lock):
    """Serialize long-running application operations without changing their bodies."""
    def decorate(function):
        @wraps(function)
        def guarded(*args, **kwargs):
            if not lock.acquire(blocking=False):
                raise RuntimeError("Another analysis or repair is running")
            try:
                return function(*args, **kwargs)
            finally:
                lock.release()
        return guarded
    return decorate
