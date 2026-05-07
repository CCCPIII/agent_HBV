import os
from contextlib import contextmanager
from typing import Iterator


_PROXY_KEYS = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "GIT_HTTP_PROXY",
    "GIT_HTTPS_PROXY",
    "git_http_proxy",
    "git_https_proxy",
]


@contextmanager
def yfinance_network_env() -> Iterator[None]:
    """Temporarily clear broken proxy env vars so yfinance can reach Yahoo directly."""
    previous = {key: os.environ.get(key) for key in _PROXY_KEYS if key in os.environ}
    try:
        for key in _PROXY_KEYS:
            os.environ.pop(key, None)
        yield
    finally:
        for key in _PROXY_KEYS:
            os.environ.pop(key, None)
        for key, value in previous.items():
            if value is not None:
                os.environ[key] = value
