#!/usr/bin/env python3
# ruff: noqa: S101
"""
webapi/auth_rate_limiter.py のユニットテスト

IPベースの認証レート制限機能を検証します。
"""

from __future__ import annotations

from unittest import mock

import price_watch.webapi.auth_rate_limiter


class TestIsLockedOut:
    """is_locked_out 関数のテスト"""

    def setup_method(self):
        """各テスト前に状態をクリア"""
        price_watch.webapi.auth_rate_limiter.clear_state()

    def test_returns_false_for_new_ip(self):
        """新規IPはロックアウトされていない"""
        result = price_watch.webapi.auth_rate_limiter.is_locked_out("192.168.1.1")

        assert result is False

    def test_returns_true_for_locked_ip(self):
        """ロックアウト中のIPはTrueを返す"""
        ip = "192.168.1.1"
        # 5回失敗させてロックアウトを発生させる
        for _ in range(5):
            price_watch.webapi.auth_rate_limiter.record_failure(ip)

        result = price_watch.webapi.auth_rate_limiter.is_locked_out(ip)

        assert result is True

    def test_returns_false_after_lockout_expires(self):
        """ロックアウト期限切れ後はFalseを返す"""
        ip = "192.168.1.1"
        # ロックアウトを発生させる
        for _ in range(5):
            price_watch.webapi.auth_rate_limiter.record_failure(ip)

        # 3時間後をシミュレート
        future_time = mock.MagicMock()
        future_time.timestamp.return_value = 9999999999.0  # 遠い未来

        with mock.patch("my_lib.time.now", return_value=future_time):
            result = price_watch.webapi.auth_rate_limiter.is_locked_out(ip)

        assert result is False


class TestRecordFailure:
    """record_failure 関数のテスト"""

    def setup_method(self):
        """各テスト前に状態をクリア"""
        price_watch.webapi.auth_rate_limiter.clear_state()

    def test_returns_false_for_first_failure(self):
        """最初の失敗ではロックアウトしない"""
        result = price_watch.webapi.auth_rate_limiter.record_failure("192.168.1.1")

        assert result is False

    def test_returns_false_for_four_failures(self):
        """4回目の失敗ではロックアウトしない"""
        ip = "192.168.1.1"
        result = False
        for _ in range(4):
            result = price_watch.webapi.auth_rate_limiter.record_failure(ip)

        assert result is False

    def test_returns_true_on_fifth_failure(self):
        """5回目の失敗でロックアウト"""
        ip = "192.168.1.1"
        results = [price_watch.webapi.auth_rate_limiter.record_failure(ip) for _ in range(5)]

        assert results == [False, False, False, False, True]

    def test_different_ips_tracked_separately(self):
        """異なるIPは別々に追跡"""
        ip1 = "192.168.1.1"
        ip2 = "192.168.1.2"

        # ip1 を4回失敗
        for _ in range(4):
            price_watch.webapi.auth_rate_limiter.record_failure(ip1)

        # ip2 を1回失敗
        price_watch.webapi.auth_rate_limiter.record_failure(ip2)

        # ip1 はまだロックアウトされていない
        assert not price_watch.webapi.auth_rate_limiter.is_locked_out(ip1)
        assert not price_watch.webapi.auth_rate_limiter.is_locked_out(ip2)

    def test_old_failures_are_cleaned_up(self):
        """10分以上前の失敗は無視される"""
        ip = "192.168.1.1"
        base_time = 1000000.0

        # 最初の4回の失敗（古い）
        old_time = mock.MagicMock()
        old_time.timestamp.return_value = base_time
        with mock.patch("my_lib.time.now", return_value=old_time):
            for _ in range(4):
                price_watch.webapi.auth_rate_limiter.record_failure(ip)

        # 11分後に1回失敗（古い失敗はクリアされているはず）
        new_time = mock.MagicMock()
        new_time.timestamp.return_value = base_time + 11 * 60  # 11分後
        with mock.patch("my_lib.time.now", return_value=new_time):
            result = price_watch.webapi.auth_rate_limiter.record_failure(ip)

        # ロックアウトは発生しない（古い4回がクリアされ、新しい1回のみ）
        assert result is False


class TestGetLockoutRemainingSec:
    """get_lockout_remaining_sec 関数のテスト"""

    def setup_method(self):
        """各テスト前に状態をクリア"""
        price_watch.webapi.auth_rate_limiter.clear_state()

    def test_returns_zero_for_new_ip(self):
        """新規IPは0を返す"""
        result = price_watch.webapi.auth_rate_limiter.get_lockout_remaining_sec("192.168.1.1")

        assert result == 0

    def test_returns_remaining_seconds(self):
        """ロックアウト中は残り時間を返す"""
        ip = "192.168.1.1"
        base_time = 1000000.0

        # ロックアウトを発生させる
        lock_time = mock.MagicMock()
        lock_time.timestamp.return_value = base_time
        with mock.patch("my_lib.time.now", return_value=lock_time):
            for _ in range(5):
                price_watch.webapi.auth_rate_limiter.record_failure(ip)

        # 1時間後に残り時間を確認
        check_time = mock.MagicMock()
        check_time.timestamp.return_value = base_time + 3600  # 1時間後
        with mock.patch("my_lib.time.now", return_value=check_time):
            result = price_watch.webapi.auth_rate_limiter.get_lockout_remaining_sec(ip)

        # 3時間 - 1時間 = 2時間 = 7200秒
        assert result == 7200


class TestRecordFailureForNotify:
    """record_failure_for_notify 関数のテスト"""

    def setup_method(self):
        """各テスト前に状態をクリア"""
        price_watch.webapi.auth_rate_limiter.clear_state()

    def test_returns_none_for_first_failure(self):
        """最初の失敗ではNoneを返す"""
        result = price_watch.webapi.auth_rate_limiter.record_failure_for_notify("192.168.1.1")

        assert result is None

    def test_returns_none_for_four_failures(self):
        """4回目の失敗ではNoneを返す"""
        ip = "192.168.1.1"
        results = [price_watch.webapi.auth_rate_limiter.record_failure_for_notify(ip) for _ in range(4)]

        assert results == [None, None, None, None]

    def test_returns_5_on_fifth_failure(self):
        """5回目の失敗で5を返す"""
        ip = "192.168.1.1"
        results = [price_watch.webapi.auth_rate_limiter.record_failure_for_notify(ip) for _ in range(5)]

        assert results == [None, None, None, None, 5]

    def test_returns_10_on_tenth_failure(self):
        """10回目の失敗で10を返す"""
        ip = "192.168.1.1"
        results = [price_watch.webapi.auth_rate_limiter.record_failure_for_notify(ip) for _ in range(10)]

        # 5, 10回目のみ値を返す
        assert results[4] == 5
        assert results[9] == 10
        assert all(r is None for r in results[:4])
        assert all(r is None for r in results[5:9])

    def test_returns_none_after_one_hour(self):
        """1時間経過後はカウントがリセットされる"""
        ip = "192.168.1.1"
        base_time = 1000000.0

        # 4回失敗
        old_time = mock.MagicMock()
        old_time.timestamp.return_value = base_time
        with mock.patch("my_lib.time.now", return_value=old_time):
            for _ in range(4):
                price_watch.webapi.auth_rate_limiter.record_failure_for_notify(ip)

        # 61分後に1回失敗（古い失敗はクリアされているはず）
        new_time = mock.MagicMock()
        new_time.timestamp.return_value = base_time + 61 * 60  # 61分後
        with mock.patch("my_lib.time.now", return_value=new_time):
            result = price_watch.webapi.auth_rate_limiter.record_failure_for_notify(ip)

        # 5の倍数ではないのでNone
        assert result is None

    def test_different_ips_tracked_separately(self):
        """異なるIPは別々に追跡"""
        ip1 = "192.168.1.1"
        ip2 = "192.168.1.2"

        # ip1 を4回失敗
        for _ in range(4):
            price_watch.webapi.auth_rate_limiter.record_failure_for_notify(ip1)

        # ip2 を5回失敗
        results_ip2 = [price_watch.webapi.auth_rate_limiter.record_failure_for_notify(ip2) for _ in range(5)]

        # ip2 だけが5を返す
        assert results_ip2[4] == 5


class TestGetHourlyFailureCount:
    """get_hourly_failure_count 関数のテスト"""

    def setup_method(self):
        """各テスト前に状態をクリア"""
        price_watch.webapi.auth_rate_limiter.clear_state()

    def test_returns_zero_for_new_ip(self):
        """新規IPは0を返す"""
        result = price_watch.webapi.auth_rate_limiter.get_hourly_failure_count("192.168.1.1")

        assert result == 0

    def test_returns_failure_count(self):
        """失敗回数を返す"""
        ip = "192.168.1.1"
        for _ in range(3):
            price_watch.webapi.auth_rate_limiter.record_failure_for_notify(ip)

        result = price_watch.webapi.auth_rate_limiter.get_hourly_failure_count(ip)

        assert result == 3

    def test_excludes_old_failures(self):
        """1時間以上前の失敗は除外"""
        ip = "192.168.1.1"
        base_time = 1000000.0

        # 古い失敗を記録
        old_time = mock.MagicMock()
        old_time.timestamp.return_value = base_time
        with mock.patch("my_lib.time.now", return_value=old_time):
            for _ in range(3):
                price_watch.webapi.auth_rate_limiter.record_failure_for_notify(ip)

        # 61分後に確認
        new_time = mock.MagicMock()
        new_time.timestamp.return_value = base_time + 61 * 60
        with mock.patch("my_lib.time.now", return_value=new_time):
            result = price_watch.webapi.auth_rate_limiter.get_hourly_failure_count(ip)

        assert result == 0


class TestClearState:
    """clear_state 関数のテスト"""

    def test_clears_all_state(self):
        """全状態をクリア"""
        ip = "192.168.1.1"
        # ロックアウトを発生させる
        for _ in range(5):
            price_watch.webapi.auth_rate_limiter.record_failure(ip)
        assert price_watch.webapi.auth_rate_limiter.is_locked_out(ip) is True

        # 状態をクリア
        price_watch.webapi.auth_rate_limiter.clear_state()

        # ロックアウトが解除されている
        assert price_watch.webapi.auth_rate_limiter.is_locked_out(ip) is False

    def test_clears_notify_state(self):
        """通知用の状態もクリア"""
        ip = "192.168.1.1"
        for _ in range(3):
            price_watch.webapi.auth_rate_limiter.record_failure_for_notify(ip)
        assert price_watch.webapi.auth_rate_limiter.get_hourly_failure_count(ip) == 3

        price_watch.webapi.auth_rate_limiter.clear_state()

        assert price_watch.webapi.auth_rate_limiter.get_hourly_failure_count(ip) == 0
