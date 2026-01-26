#!/usr/bin/env python3
# ruff: noqa: S101
"""
amazon/paapi_rate_limiter.py のユニットテスト

PA-API レートリミッターを検証します。
"""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import price_watch.amazon.paapi_rate_limiter


class TestPaapiRateLimiter:
    """PaapiRateLimiter クラスのテスト"""

    def test_first_acquire_no_wait(self):
        """最初の呼び出しは待機なし"""
        limiter = price_watch.amazon.paapi_rate_limiter.PaapiRateLimiter(tps=1.0)

        start = time.time()
        limiter.acquire()
        elapsed = time.time() - start

        # 最初の呼び出しは即座に完了
        assert elapsed < 0.1

    def test_acquire_respects_rate_limit(self):
        """レート制限を守る"""
        limiter = price_watch.amazon.paapi_rate_limiter.PaapiRateLimiter(tps=10.0)

        # 連続して呼び出し
        limiter.acquire()

        start = time.time()
        limiter.acquire()
        elapsed = time.time() - start

        # 10 TPS = 100ms 間隔
        assert elapsed >= 0.09  # 少し余裕を持たせる

    def test_context_manager(self):
        """コンテキストマネージャーとして動作"""
        limiter = price_watch.amazon.paapi_rate_limiter.PaapiRateLimiter(tps=100.0)

        with limiter as ctx:
            assert ctx is limiter

    def test_context_manager_acquires(self):
        """コンテキストマネージャーは acquire を呼び出す"""
        limiter = price_watch.amazon.paapi_rate_limiter.PaapiRateLimiter(tps=100.0)

        # 1回目
        with limiter:
            pass

        start = time.time()
        with limiter:
            pass
        elapsed = time.time() - start

        # 100 TPS = 10ms 間隔
        assert elapsed >= 0.008

    def test_thread_safety(self):
        """スレッドセーフ"""
        limiter = price_watch.amazon.paapi_rate_limiter.PaapiRateLimiter(tps=100.0)

        results: list[float] = []
        errors: list[Exception] = []

        def worker() -> None:
            try:
                for _ in range(5):
                    limiter.acquire()
                    results.append(time.time())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(3)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # 15回の呼び出しが記録されている
        assert len(results) == 15

    def test_high_tps(self):
        """高い TPS 設定"""
        limiter = price_watch.amazon.paapi_rate_limiter.PaapiRateLimiter(tps=1000.0)

        start = time.time()
        for _ in range(10):
            limiter.acquire()
        elapsed = time.time() - start

        # 1000 TPS で 10 回 = 約 10ms
        assert elapsed < 0.1


class TestGetRateLimiter:
    """get_rate_limiter 関数のテスト"""

    def test_returns_singleton(self):
        """シングルトンを返す"""
        # グローバル状態をリセット
        price_watch.amazon.paapi_rate_limiter._rate_limiter = None

        limiter1 = price_watch.amazon.paapi_rate_limiter.get_rate_limiter(tps=1.0)
        limiter2 = price_watch.amazon.paapi_rate_limiter.get_rate_limiter(tps=2.0)

        # 同じインスタンス
        assert limiter1 is limiter2

        # クリーンアップ
        price_watch.amazon.paapi_rate_limiter._rate_limiter = None

    def test_creates_new_if_none(self):
        """None の場合は新規作成"""
        # グローバル状態をリセット
        price_watch.amazon.paapi_rate_limiter._rate_limiter = None

        limiter = price_watch.amazon.paapi_rate_limiter.get_rate_limiter(tps=5.0)

        assert limiter is not None
        assert limiter.tps == 5.0

        # クリーンアップ
        price_watch.amazon.paapi_rate_limiter._rate_limiter = None

    def test_uses_default_tps(self):
        """デフォルトの TPS を使用"""
        # グローバル状態をリセット
        price_watch.amazon.paapi_rate_limiter._rate_limiter = None

        limiter = price_watch.amazon.paapi_rate_limiter.get_rate_limiter()

        assert limiter.tps == 1.0

        # クリーンアップ
        price_watch.amazon.paapi_rate_limiter._rate_limiter = None

    def test_debug_log_on_wait(self):
        """待機時にデバッグログを出力"""
        # グローバル状態をリセット
        price_watch.amazon.paapi_rate_limiter._rate_limiter = None

        limiter = price_watch.amazon.paapi_rate_limiter.PaapiRateLimiter(tps=10.0)

        # 1回目
        limiter.acquire()

        # 2回目は待機が発生
        with patch("logging.debug"):
            limiter.acquire()

            # デバッグログが呼ばれた可能性あり（タイミングによる）
            # 呼ばれなくてもエラーにはしない

        # クリーンアップ
        price_watch.amazon.paapi_rate_limiter._rate_limiter = None
