"""Keep request starts for a shared HTTP host spaced across adapter threads."""

from threading import Lock
from time import monotonic
from time import sleep as default_sleep
from urllib.parse import urlsplit

_LOCK = Lock()
_HOST_LOCKS = {}
_NEXT_REQUEST = {}


def pace_request(url: str, interval: float = 0.5, *, sleep=default_sleep) -> None:
    if not interval:
        return
    host = urlsplit(url).hostname
    with _LOCK:
        host_lock = _HOST_LOCKS.setdefault(host, Lock())
    with host_lock:
        wait = _NEXT_REQUEST.get(host, 0) - monotonic()
        if wait > 0:
            sleep(wait)
        _NEXT_REQUEST[host] = monotonic() + interval
