"""
PA-API レートリミッター

Amazon Product Advertising API のレート制限（TPS）を管理します。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field


@dataclass
class PaapiRateLimiter:
    """PA-API レートリミッター

    TPS（Transactions Per Second）制限に従い、API 呼び出しの間隔を制御します。
    """

    tps: float = 1.0
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _last_call_time: float = field(default=0.0, init=False)

    def acquire(self) -> None:
        """レート制限に従い、必要であれば待機してから通過を許可."""
        with self._lock:
            current_time = time.time()
            min_interval = 1.0 / self.tps
            elapsed = current_time - self._last_call_time

            if elapsed < min_interval:
                wait_time = min_interval - elapsed
                logging.debug("PA-API rate limit: waiting %.3f seconds", wait_time)
                time.sleep(wait_time)

            self._last_call_time = time.time()

    def __enter__(self) -> PaapiRateLimiter:
        """コンテキストマネージャーとして使用可能."""
        self.acquire()
        return self

    def __exit__(self, _exc_type: object, _exc_val: object, _exc_tb: object) -> None:
        """コンテキストマネージャー終了時は何もしない."""


# モジュールレベルのレートリミッター（シングルトン）
_rate_limiter: PaapiRateLimiter | None = None


def get_rate_limiter(tps: float = 1.0) -> PaapiRateLimiter:
    """レートリミッターを取得（シングルトン）."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = PaapiRateLimiter(tps=tps)
    return _rate_limiter
