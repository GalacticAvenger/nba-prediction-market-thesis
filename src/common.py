"""Shared API/cache helpers for thesis data collection."""
from __future__ import annotations

import json
import os
import re
import time
import threading
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
_request_lock = threading.Lock()
_last_request_at = 0.0


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": "senior-thesis-research/1.0", "Accept": "application/json"})
    retry = Retry(total=6, connect=4, read=4, status=5, backoff_factor=1.0,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset({"GET"}), respect_retry_after_header=True)
    session.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=16))
    return session


def get_json(session: requests.Session, url: str, cache_path: Path, *, min_interval: float = 0.0) -> Any:
    """Read cached JSON or fetch once, writing the exact response body atomically."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists():
        with cache_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    # Respect the minimum interval across worker threads, not once per thread.
    # Kalshi starts returning 429s if concurrent workers each apply the delay
    # independently and collectively exceed the public API limit.
    global _last_request_at
    wait_interval = max(min_interval, 0.4 if "kalshi.com" in url else min_interval)
    for attempt in range(7):
        with _request_lock:
            wait = wait_interval - (time.monotonic() - _last_request_at)
            if wait > 0:
                time.sleep(wait)
            _last_request_at = time.monotonic()
        try:
            response = session.get(url, timeout=(15, 90))
            response.raise_for_status()
            break
        except (requests.exceptions.RetryError, requests.exceptions.HTTPError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status != 429 and "429" not in str(exc):
                raise
            if attempt == 6:
                raise
            time.sleep(min(60, 5 * (2 ** attempt)))
    temporary = cache_path.with_suffix(cache_path.suffix + f".{os.getpid()}.tmp")
    temporary.write_bytes(response.content)
    temporary.replace(cache_path)
    return response.json()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
