#!/usr/bin/env python3
# ruff: noqa: S101
"""
managers/metrics_manager.py のユニットテスト

メトリクス管理を検証します。
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import price_watch.managers.metrics_manager


class TestMetricsManagerInitialize:
    """MetricsManager の initialize テスト"""

    def test_initialize_creates_db(self, tmp_path: pathlib.Path) -> None:
        """initialize でデータベースを作成"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)

        with patch("price_watch.metrics.MetricsDB") as mock_db_class:
            manager.initialize()

        mock_db_class.assert_called_once()

    def test_initialize_idempotent(self, tmp_path: pathlib.Path) -> None:
        """initialize は冪等（2回呼んでも1回だけ初期化）"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        mock_db = MagicMock()

        with patch("price_watch.metrics.MetricsDB", return_value=mock_db) as mock_class:
            manager.initialize()
            manager.initialize()

        mock_class.assert_called_once()


class TestMetricsManagerProperties:
    """MetricsManager のプロパティテスト"""

    def test_db_returns_none_before_init(self, tmp_path: pathlib.Path) -> None:
        """初期化前は db は None"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        assert manager.db is None

    def test_db_returns_instance_after_init(self, tmp_path: pathlib.Path) -> None:
        """初期化後は db はインスタンスを返す"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        mock_db = MagicMock()

        with patch("price_watch.metrics.MetricsDB", return_value=mock_db):
            manager.initialize()

        assert manager.db is mock_db

    def test_current_session_id_returns_none_initially(self, tmp_path: pathlib.Path) -> None:
        """初期状態では current_session_id は None"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        assert manager.current_session_id is None


class TestStartSession:
    """start_session メソッドのテスト"""

    def test_returns_none_if_db_not_initialized(self, tmp_path: pathlib.Path) -> None:
        """DB 未初期化時は None を返す"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        result = manager.start_session()
        assert result is None

    def test_starts_session(self, tmp_path: pathlib.Path) -> None:
        """セッションを開始"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        mock_db = MagicMock()
        mock_db.start_session.return_value = 123
        manager._db = mock_db

        result = manager.start_session()

        assert result == 123
        assert manager._current_session_id == 123
        assert manager._session_total_items == 0
        assert manager._session_success_items == 0
        assert manager._session_failed_items == 0


class TestEndSession:
    """end_session メソッドのテスト"""

    def test_does_nothing_if_db_not_initialized(self, tmp_path: pathlib.Path) -> None:
        """DB 未初期化時は何もしない"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        manager.end_session("normal")
        # No exception raised

    def test_does_nothing_if_no_session(self, tmp_path: pathlib.Path) -> None:
        """セッションがない場合は何もしない"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        mock_db = MagicMock()
        manager._db = mock_db

        manager.end_session("normal")

        mock_db.end_session.assert_not_called()

    def test_ends_session(self, tmp_path: pathlib.Path) -> None:
        """セッションを終了"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        mock_db = MagicMock()
        manager._db = mock_db
        manager._current_session_id = 123
        manager._session_total_items = 10
        manager._session_success_items = 8
        manager._session_failed_items = 2

        manager.end_session("normal")

        mock_db.end_session.assert_called_once()
        assert manager._current_session_id is None

    def test_ends_session_with_work_ended_at(self, tmp_path: pathlib.Path) -> None:
        """作業終了時刻付きでセッションを終了"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        mock_db = MagicMock()
        manager._db = mock_db
        manager._current_session_id = 123

        mock_now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        with patch("my_lib.time.now", return_value=mock_now):
            manager.end_session("normal", work_ended_at=1705320000.0)

        mock_db.end_session.assert_called_once()

    def test_ends_session_with_stored_work_ended_at(self, tmp_path: pathlib.Path) -> None:
        """保存された作業終了時刻を使用"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        mock_db = MagicMock()
        manager._db = mock_db
        manager._current_session_id = 123
        manager._work_ended_at = 1705320000.0

        mock_now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        with patch("my_lib.time.now", return_value=mock_now):
            manager.end_session("normal")

        mock_db.end_session.assert_called_once()


class TestRecordWorkEnded:
    """record_work_ended メソッドのテスト"""

    def test_records_timestamp(self, tmp_path: pathlib.Path) -> None:
        """タイムスタンプを記録"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        manager.record_work_ended(1705320000.0)
        assert manager._work_ended_at == 1705320000.0


class TestRecordItemResult:
    """record_item_result メソッドのテスト"""

    def test_records_success(self, tmp_path: pathlib.Path) -> None:
        """成功を記録"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        manager.record_item_result(success=True)

        assert manager._session_total_items == 1
        assert manager._session_success_items == 1
        assert manager._session_failed_items == 0

    def test_records_failure(self, tmp_path: pathlib.Path) -> None:
        """失敗を記録"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        manager.record_item_result(success=False)

        assert manager._session_total_items == 1
        assert manager._session_success_items == 0
        assert manager._session_failed_items == 1


class TestUpdateHeartbeat:
    """update_heartbeat メソッドのテスト"""

    def test_does_nothing_if_db_not_initialized(self, tmp_path: pathlib.Path) -> None:
        """DB 未初期化時は何もしない"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        manager.update_heartbeat()
        # No exception raised

    def test_does_nothing_if_no_session(self, tmp_path: pathlib.Path) -> None:
        """セッションがない場合は何もしない"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        mock_db = MagicMock()
        manager._db = mock_db

        manager.update_heartbeat()

        mock_db.update_heartbeat.assert_not_called()

    def test_updates_heartbeat(self, tmp_path: pathlib.Path) -> None:
        """ハートビートを更新"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        mock_db = MagicMock()
        manager._db = mock_db
        manager._current_session_id = 123

        manager.update_heartbeat()

        mock_db.update_heartbeat.assert_called_once_with(
            123,
            total_items=0,
            success_items=0,
            failed_items=0,
        )


class TestStartStoreCrawl:
    """start_store_crawl メソッドのテスト"""

    def test_returns_none_if_db_not_initialized(self, tmp_path: pathlib.Path) -> None:
        """DB 未初期化時は None を返す"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        result = manager.start_store_crawl("test-store")
        assert result is None

    def test_returns_none_if_no_session(self, tmp_path: pathlib.Path) -> None:
        """セッションがない場合は None を返す"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        mock_db = MagicMock()
        manager._db = mock_db

        result = manager.start_store_crawl("test-store")

        assert result is None

    def test_starts_store_crawl(self, tmp_path: pathlib.Path) -> None:
        """ストア巡回を開始"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        mock_db = MagicMock()
        mock_db.start_store_crawl.return_value = 456
        manager._db = mock_db
        manager._current_session_id = 123

        result = manager.start_store_crawl("test-store")

        assert result == 456
        mock_db.start_store_crawl.assert_called_once_with(123, "test-store")


class TestEndStoreCrawl:
    """end_store_crawl メソッドのテスト"""

    def test_does_nothing_if_db_not_initialized(self, tmp_path: pathlib.Path) -> None:
        """DB 未初期化時は何もしない"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        manager.end_store_crawl(456, 10, 8, 2)
        # No exception raised

    def test_does_nothing_if_stats_id_is_none(self, tmp_path: pathlib.Path) -> None:
        """stats_id が None の場合は何もしない"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        mock_db = MagicMock()
        manager._db = mock_db

        manager.end_store_crawl(None, 10, 8, 2)

        mock_db.end_store_crawl.assert_not_called()

    def test_ends_store_crawl(self, tmp_path: pathlib.Path) -> None:
        """ストア巡回を終了"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        mock_db = MagicMock()
        manager._db = mock_db

        manager.end_store_crawl(456, 10, 8, 2)

        mock_db.end_store_crawl.assert_called_once_with(456, 10, 8, 2)


class TestStoreContext:
    """StoreContext のテスト"""

    def test_context_manager_starts_and_ends(self, tmp_path: pathlib.Path) -> None:
        """コンテキストマネージャーで開始・終了"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        mock_db = MagicMock()
        mock_db.start_store_crawl.return_value = 456
        manager._db = mock_db
        manager._current_session_id = 123

        with price_watch.managers.metrics_manager.StoreContext(metrics=manager, store_name="test-store"):
            pass

        mock_db.start_store_crawl.assert_called_once()
        mock_db.end_store_crawl.assert_called_once()

    def test_record_success(self, tmp_path: pathlib.Path) -> None:
        """成功を記録"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        mock_db = MagicMock()
        mock_db.start_store_crawl.return_value = 456
        manager._db = mock_db
        manager._current_session_id = 123

        with price_watch.managers.metrics_manager.StoreContext(
            metrics=manager, store_name="test-store"
        ) as ctx:
            ctx.record_success()
            ctx.record_success()

        assert ctx._item_count == 2
        assert ctx._success_count == 2
        assert ctx._failed_count == 0
        mock_db.end_store_crawl.assert_called_once_with(456, 2, 2, 0)

    def test_record_failure(self, tmp_path: pathlib.Path) -> None:
        """失敗を記録"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        mock_db = MagicMock()
        mock_db.start_store_crawl.return_value = 456
        manager._db = mock_db
        manager._current_session_id = 123

        with price_watch.managers.metrics_manager.StoreContext(
            metrics=manager, store_name="test-store"
        ) as ctx:
            ctx.record_failure()

        assert ctx._item_count == 1
        assert ctx._success_count == 0
        assert ctx._failed_count == 1
        mock_db.end_store_crawl.assert_called_once_with(456, 1, 0, 1)

    def test_enter_returns_self(self, tmp_path: pathlib.Path) -> None:
        """__enter__ は self を返す"""
        manager = price_watch.managers.metrics_manager.MetricsManager(metrics_dir=tmp_path)
        ctx = price_watch.managers.metrics_manager.StoreContext(metrics=manager, store_name="test-store")

        with ctx as result:
            assert result is ctx
