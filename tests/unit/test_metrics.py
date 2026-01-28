#!/usr/bin/env python3
# ruff: noqa: S101
"""
metrics.py のユニットテスト
"""

import pathlib
import tempfile
import time
from datetime import datetime, timedelta

import my_lib.time
import pytest

from price_watch.metrics import (
    BoxPlotStats,
    CrawlTimeBoxPlotData,
    CurrentSessionStatus,
    FailureTimeseriesData,
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
        today = my_lib.time.now().strftime("%Y-%m-%d")
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

        today = my_lib.time.now().strftime("%Y-%m-%d")
        heatmap = metrics_db.get_uptime_heatmap(today, today)

        # 少なくとも現在時刻のセルは稼働率 > 0
        assert any(cell.uptime_rate > 0 for cell in heatmap.cells)

    def test_heatmap_date_range(self, metrics_db):
        """日付範囲のヒートマップ"""
        today = my_lib.time.now()
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
            work_ended_at=None,
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
            is_crawling=True,
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

    def test_boxplot_stats_frozen(self):
        """BoxPlotStats は不変"""
        stats = BoxPlotStats(min=1.0, q1=2.0, median=3.0, q3=4.0, max=5.0, count=10)
        with pytest.raises(AttributeError):
            stats.min = 0.0  # type: ignore


class TestCrawlTimeBoxPlot:
    """箱ひげ図統計のテスト"""

    def test_compute_boxplot_stats_empty(self):
        """空リストの場合は None"""
        result = MetricsDB._compute_boxplot_stats([])
        assert result is None

    def test_compute_boxplot_stats_single(self):
        """要素1つの場合"""
        result = MetricsDB._compute_boxplot_stats([5.0])
        assert result is not None
        assert result.min == 5.0
        assert result.median == 5.0
        assert result.max == 5.0
        assert result.count == 1

    def test_compute_boxplot_stats_multiple(self):
        """複数要素の場合"""
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result = MetricsDB._compute_boxplot_stats(values)
        assert result is not None
        assert result.count == 10
        assert result.median == 5.5
        assert result.min <= result.q1 <= result.median <= result.q3 <= result.max

    def test_compute_boxplot_stats_outliers(self):
        """外れ値の検出"""
        # 正常範囲: 1-10, 外れ値: 100
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 100.0]
        result = MetricsDB._compute_boxplot_stats(values)
        assert result is not None
        assert 100.0 in result.outliers

    def test_compute_boxplot_stats_two_elements(self):
        """要素2つの場合"""
        result = MetricsDB._compute_boxplot_stats([3.0, 7.0])
        assert result is not None
        assert result.count == 2
        assert result.q1 == 3.0
        assert result.q3 == 7.0
        assert result.median == 5.0

    def test_get_crawl_time_boxplot(self, metrics_db):
        """箱ひげ図データの取得"""
        session_id = metrics_db.start_session()

        # ストア巡回を記録
        for _ in range(3):
            stats_id = metrics_db.start_store_crawl(session_id, "store-a.com")
            metrics_db.end_store_crawl(stats_id, 5, 4, 1)

        metrics_db.end_session(session_id, 15, 12, 3)

        data = metrics_db.get_crawl_time_boxplot(days=7)
        assert isinstance(data, CrawlTimeBoxPlotData)
        assert "store-a.com" in data.stores
        assert data.stores["store-a.com"].count == 3
        assert data.total is not None
        assert data.total.count == 1

    def test_get_crawl_time_boxplot_empty(self, metrics_db):
        """データがない場合"""
        data = metrics_db.get_crawl_time_boxplot(days=7)
        assert isinstance(data, CrawlTimeBoxPlotData)
        assert data.stores == {}
        assert data.total is None


class TestFailureTimeseries:
    """失敗数時系列のテスト"""

    def test_get_failure_timeseries_empty(self, metrics_db):
        """データがない場合"""
        data = metrics_db.get_failure_timeseries(days=1)
        assert isinstance(data, FailureTimeseriesData)
        assert len(data.labels) > 0
        assert all(v == 0 for v in data.data)

    def test_get_failure_timeseries_with_data(self, metrics_db):
        """失敗データがある場合"""
        session_id = metrics_db.start_session()

        stats_id = metrics_db.start_store_crawl(session_id, "store-a.com")
        metrics_db.end_store_crawl(stats_id, 5, 3, 2)

        stats_id2 = metrics_db.start_store_crawl(session_id, "store-b.com")
        metrics_db.end_store_crawl(stats_id2, 3, 1, 2)

        data = metrics_db.get_failure_timeseries(days=1)
        assert isinstance(data, FailureTimeseriesData)
        # 失敗データが含まれている
        assert sum(data.data) == 4  # 2 + 2

    def test_get_failure_timeseries_labels_hourly(self, metrics_db):
        """ラベルが1時間単位で生成される"""
        data = metrics_db.get_failure_timeseries(days=1)
        # 24時間 + 現在の時間 = 少なくとも24個のラベル
        assert len(data.labels) >= 24
        assert len(data.labels) == len(data.data)


class TestEndSessionUptime:
    """end_session の稼働率修正テスト"""

    def test_ended_at_is_current_time(self, metrics_db):
        """ended_at が現在時刻になること"""
        import sqlite3

        session_id = metrics_db.start_session()

        # 作業終了時刻を過去に設定
        work_ended = my_lib.time.now() - timedelta(minutes=30)
        before_end = my_lib.time.now()
        metrics_db.end_session(session_id, 10, 8, 2, "normal", work_ended_at=work_ended)
        after_end = my_lib.time.now()

        # DB から ended_at, work_ended_at を直接取得
        with sqlite3.connect(metrics_db.db_path) as conn:
            cursor = conn.execute(
                "SELECT ended_at, work_ended_at FROM crawl_sessions WHERE id = ?", (session_id,)
            )
            row = cursor.fetchone()
            ended_at = datetime.fromisoformat(row[0])
            db_work_ended_at = datetime.fromisoformat(row[1])

        # ended_at は現在時刻付近（work_ended_at ではない）
        if before_end.tzinfo:
            ended_at = ended_at.replace(tzinfo=before_end.tzinfo)
            db_work_ended_at = db_work_ended_at.replace(tzinfo=before_end.tzinfo)
        assert ended_at >= before_end - timedelta(seconds=1)
        assert ended_at <= after_end + timedelta(seconds=1)

        # work_ended_at は指定した値と一致
        assert abs((db_work_ended_at - work_ended).total_seconds()) < 1

    def test_duration_based_on_work_ended_at(self, metrics_db):
        """duration_sec が work_ended_at 基準になること"""
        session_id = metrics_db.start_session()

        # セッション開始から少し待つ
        time.sleep(0.1)

        # 作業終了時刻を設定（開始から約0.1秒後）
        work_ended = my_lib.time.now()

        # さらに待つ（sleep 模擬）
        time.sleep(0.1)

        metrics_db.end_session(session_id, 10, 8, 2, "normal", work_ended_at=work_ended)

        sessions = metrics_db.get_sessions(limit=1)
        assert len(sessions) == 1
        # duration は work_ended_at 基準（短い方）
        assert sessions[0].duration_sec is not None
        # duration は 0.5秒未満のはず（sleep 期間を含まない）
        assert sessions[0].duration_sec < 0.5

    def test_duration_without_work_ended_at(self, metrics_db):
        """work_ended_at なしの場合は現在時刻基準"""
        session_id = metrics_db.start_session()
        time.sleep(0.1)
        metrics_db.end_session(session_id, 10, 8, 2, "normal")

        sessions = metrics_db.get_sessions(limit=1)
        assert len(sessions) == 1
        assert sessions[0].duration_sec is not None
        assert sessions[0].duration_sec >= 0.05
        # work_ended_at も設定される（ended_at と同じ値）
        assert sessions[0].work_ended_at is not None
