#!/usr/bin/env python3
# ruff: noqa: S101
"""
metrics.py のユニットテスト
"""

import pathlib
import tempfile
import time
from datetime import UTC, datetime, timedelta

import pytest

from price_watch.metrics import (
    CurrentSessionStatus,
    HeatmapCell,
    HeatmapData,
    MetricsDB,
    SessionInfo,
    StoreStats,
)


@pytest.fixture
def temp_db():
    """一時的なデータベースを作成"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = pathlib.Path(tmpdir) / "test_metrics.db"
        yield db_path


@pytest.fixture
def metrics_db(temp_db):
    """MetricsDB インスタンスを作成"""
    return MetricsDB(temp_db)


class TestMetricsDBInit:
    """MetricsDB 初期化のテスト"""

    def test_create_db(self, temp_db):
        """データベースが作成される"""
        db = MetricsDB(temp_db)
        assert temp_db.exists()
        assert db.db_path == temp_db

    def test_create_tables(self, temp_db):
        """テーブルが作成される"""
        import sqlite3

        db = MetricsDB(temp_db)
        with sqlite3.connect(db.db_path) as conn:
            # テーブル一覧を取得
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}

        assert "schema_version" in tables
        assert "crawl_sessions" in tables
        assert "store_crawl_stats" in tables


class TestSessionManagement:
    """セッション管理のテスト"""

    def test_start_session(self, metrics_db):
        """セッションを開始できる"""
        session_id = metrics_db.start_session()
        assert session_id > 0

    def test_start_session_returns_different_ids(self, metrics_db):
        """複数のセッションは異なるIDを持つ"""
        # 最初のセッションを終了
        session_id1 = metrics_db.start_session()
        metrics_db.end_session(session_id1, 0, 0, 0, "normal")

        # 2番目のセッション
        session_id2 = metrics_db.start_session()
        assert session_id2 != session_id1

    def test_end_session(self, metrics_db):
        """セッションを終了できる"""
        session_id = metrics_db.start_session()
        metrics_db.end_session(session_id, 10, 8, 2, "normal")

        sessions = metrics_db.get_sessions(limit=1)
        assert len(sessions) == 1
        assert sessions[0].total_items == 10
        assert sessions[0].success_items == 8
        assert sessions[0].failed_items == 2
        assert sessions[0].exit_reason == "normal"
        assert sessions[0].ended_at is not None

    def test_update_heartbeat(self, metrics_db):
        """ハートビートを更新できる"""
        session_id = metrics_db.start_session()

        # 少し待ってからハートビート更新
        time.sleep(0.1)
        metrics_db.update_heartbeat(session_id)

        status = metrics_db.get_current_session_status()
        assert status.is_running
        assert status.last_heartbeat_at is not None

    def test_close_orphan_sessions(self, metrics_db):
        """孤児セッションが閉じられる"""
        # 最初のセッション（終了しない）
        session_id1 = metrics_db.start_session()

        # 2番目のセッションを開始すると、1番目は superseded になる
        session_id2 = metrics_db.start_session()

        sessions = metrics_db.get_sessions(limit=10)
        # 新しい順なので session_id2 が最初
        orphan_session = next(s for s in sessions if s.id == session_id1)
        assert orphan_session.exit_reason == "superseded"
        assert orphan_session.ended_at is not None

        # session_id2 はまだ実行中
        current = next(s for s in sessions if s.id == session_id2)
        assert current.ended_at is None


class TestStoreCrawlStats:
    """ストア統計のテスト"""

    def test_start_and_end_store_crawl(self, metrics_db):
        """ストア巡回を開始・終了できる"""
        session_id = metrics_db.start_session()
        stats_id = metrics_db.start_store_crawl(session_id, "test-store.com")

        assert stats_id > 0

        metrics_db.end_store_crawl(stats_id, 5, 4, 1)

        stats = metrics_db.get_store_stats(store_name="test-store.com", limit=1)
        assert len(stats) == 1
        assert stats[0].store_name == "test-store.com"
        assert stats[0].item_count == 5
        assert stats[0].success_count == 4
        assert stats[0].failed_count == 1
        assert stats[0].duration_sec is not None

    def test_multiple_stores_in_session(self, metrics_db):
        """1セッションで複数ストアを記録できる"""
        session_id = metrics_db.start_session()

        # ストア1
        stats_id1 = metrics_db.start_store_crawl(session_id, "store-a.com")
        metrics_db.end_store_crawl(stats_id1, 3, 3, 0)

        # ストア2
        stats_id2 = metrics_db.start_store_crawl(session_id, "store-b.com")
        metrics_db.end_store_crawl(stats_id2, 5, 4, 1)

        stats = metrics_db.get_store_stats(limit=10)
        assert len(stats) == 2

        store_names = {s.store_name for s in stats}
        assert "store-a.com" in store_names
        assert "store-b.com" in store_names


class TestCurrentSessionStatus:
    """現在のセッション状態のテスト"""

    def test_no_session(self, metrics_db):
        """セッションがない場合"""
        status = metrics_db.get_current_session_status()
        assert not status.is_running
        assert status.session_id is None
        assert status.uptime_sec is None

    def test_running_session(self, metrics_db):
        """実行中のセッションがある場合"""
        session_id = metrics_db.start_session()

        status = metrics_db.get_current_session_status()
        assert status.is_running
        assert status.session_id == session_id
        assert status.uptime_sec is not None
        assert status.uptime_sec >= 0

    def test_ended_session(self, metrics_db):
        """終了したセッションのみの場合"""
        session_id = metrics_db.start_session()
        metrics_db.end_session(session_id, 0, 0, 0, "normal")

        status = metrics_db.get_current_session_status()
        assert not status.is_running


class TestCrawlerHealthCheck:
    """クローラ健全性チェックのテスト"""

    def test_healthy_crawler(self, metrics_db):
        """健全なクローラ"""
        session_id = metrics_db.start_session()
        metrics_db.update_heartbeat(session_id)

        assert metrics_db.is_crawler_healthy(max_age_sec=600)

    def test_unhealthy_no_session(self, metrics_db):
        """セッションがない場合は不健全"""
        assert not metrics_db.is_crawler_healthy()

    def test_unhealthy_ended_session(self, metrics_db):
        """終了したセッションのみは不健全"""
        session_id = metrics_db.start_session()
        metrics_db.end_session(session_id, 0, 0, 0, "normal")

        assert not metrics_db.is_crawler_healthy()


class TestHeatmap:
    """ヒートマップのテスト"""

    def test_empty_heatmap(self, metrics_db):
        """セッションがない場合のヒートマップ"""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        heatmap = metrics_db.get_uptime_heatmap(today, today)

        assert isinstance(heatmap, HeatmapData)
        assert len(heatmap.dates) == 1
        assert heatmap.hours == list(range(24))
        # 全てのセルは稼働率0
        for cell in heatmap.cells:
            assert cell.uptime_rate == 0.0

    def test_heatmap_with_session(self, metrics_db):
        """セッションがある場合のヒートマップ"""
        # セッションを開始
        session_id = metrics_db.start_session()
        metrics_db.update_heartbeat(session_id)

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        heatmap = metrics_db.get_uptime_heatmap(today, today)

        # 少なくとも現在時刻のセルは稼働率 > 0
        assert any(cell.uptime_rate > 0 for cell in heatmap.cells)

    def test_heatmap_date_range(self, metrics_db):
        """日付範囲のヒートマップ"""
        today = datetime.now(UTC)
        start_date = (today - timedelta(days=2)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        heatmap = metrics_db.get_uptime_heatmap(start_date, end_date)

        assert len(heatmap.dates) == 3


class TestGetSessions:
    """セッション取得のテスト"""

    def test_get_sessions_empty(self, metrics_db):
        """セッションがない場合"""
        sessions = metrics_db.get_sessions()
        assert sessions == []

    def test_get_sessions_with_limit(self, metrics_db):
        """limit パラメータが機能する"""
        # 3つのセッションを作成
        for _ in range(3):
            session_id = metrics_db.start_session()
            metrics_db.end_session(session_id, 0, 0, 0, "normal")

        sessions = metrics_db.get_sessions(limit=2)
        assert len(sessions) == 2

    def test_get_sessions_order(self, metrics_db):
        """新しい順にソートされる"""
        session_id1 = metrics_db.start_session()
        metrics_db.end_session(session_id1, 0, 0, 0, "normal")

        session_id2 = metrics_db.start_session()
        metrics_db.end_session(session_id2, 0, 0, 0, "normal")

        sessions = metrics_db.get_sessions()
        assert sessions[0].id == session_id2
        assert sessions[1].id == session_id1


class TestGetStoreStats:
    """ストア統計取得のテスト"""

    def test_filter_by_store_name(self, metrics_db):
        """ストア名でフィルタできる"""
        session_id = metrics_db.start_session()

        stats_id1 = metrics_db.start_store_crawl(session_id, "store-a.com")
        metrics_db.end_store_crawl(stats_id1, 1, 1, 0)

        stats_id2 = metrics_db.start_store_crawl(session_id, "store-b.com")
        metrics_db.end_store_crawl(stats_id2, 2, 2, 0)

        stats_a = metrics_db.get_store_stats(store_name="store-a.com")
        assert len(stats_a) == 1
        assert stats_a[0].store_name == "store-a.com"

        stats_b = metrics_db.get_store_stats(store_name="store-b.com")
        assert len(stats_b) == 1
        assert stats_b[0].store_name == "store-b.com"


class TestDataclasses:
    """データクラスのテスト"""

    def test_session_info_frozen(self):
        """SessionInfo は不変"""
        info = SessionInfo(
            id=1,
            started_at=datetime.now(),
            last_heartbeat_at=None,
            ended_at=None,
            duration_sec=None,
            total_items=0,
            success_items=0,
            failed_items=0,
            exit_reason=None,
        )
        with pytest.raises(AttributeError):
            info.id = 2  # type: ignore

    def test_store_stats_frozen(self):
        """StoreStats は不変"""
        stats = StoreStats(
            id=1,
            session_id=1,
            store_name="test",
            started_at=datetime.now(),
            ended_at=None,
            duration_sec=None,
            item_count=0,
            success_count=0,
            failed_count=0,
        )
        with pytest.raises(AttributeError):
            stats.id = 2  # type: ignore

    def test_heatmap_cell_frozen(self):
        """HeatmapCell は不変"""
        cell = HeatmapCell(date="2024-01-01", hour=12, uptime_rate=0.5)
        with pytest.raises(AttributeError):
            cell.hour = 13  # type: ignore

    def test_current_session_status_frozen(self):
        """CurrentSessionStatus は不変"""
        status = CurrentSessionStatus(
            is_running=True,
            session_id=1,
            started_at=datetime.now(),
            last_heartbeat_at=datetime.now(),
            uptime_sec=100.0,
            total_items=10,
            success_items=8,
            failed_items=2,
        )
        with pytest.raises(AttributeError):
            status.is_running = False  # type: ignore
