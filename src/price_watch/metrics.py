#!/usr/bin/env python3
"""
巡回メトリクスの記録・取得

巡回セッション、ストアごとの統計、ヒートマップ用データを管理します。
"""

from __future__ import annotations

import logging
import pathlib
import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import my_lib.time

import price_watch.const


@dataclass(frozen=True)
class SessionInfo:
    """セッション情報"""

    id: int
    started_at: datetime
    last_heartbeat_at: datetime | None
    ended_at: datetime | None
    work_ended_at: datetime | None
    duration_sec: float | None
    total_items: int
    success_items: int
    failed_items: int
    exit_reason: str | None


@dataclass(frozen=True)
class StoreStats:
    """ストア統計情報"""

    id: int
    session_id: int
    store_name: str
    started_at: datetime
    ended_at: datetime | None
    duration_sec: float | None
    item_count: int
    success_count: int
    failed_count: int


@dataclass(frozen=True)
class HeatmapCell:
    """ヒートマップのセル"""

    date: str  # YYYY-MM-DD
    hour: int  # 0-23
    uptime_rate: float  # 0.0-1.0


@dataclass(frozen=True)
class HeatmapData:
    """ヒートマップデータ"""

    dates: list[str]
    hours: list[int]
    cells: list[HeatmapCell]


@dataclass(frozen=True)
class CurrentSessionStatus:
    """現在のセッション状態"""

    is_running: bool
    is_crawling: bool  # True: 巡回中, False: スリープ中（is_running=True の場合のみ意味がある）
    session_id: int | None
    started_at: datetime | None
    last_heartbeat_at: datetime | None
    uptime_sec: float | None
    total_items: int
    success_items: int
    failed_items: int


@dataclass(frozen=True)
class BoxPlotStats:
    """箱ひげ図統計"""

    min: float
    q1: float
    median: float
    q3: float
    max: float
    count: int
    outliers: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class CrawlTimeBoxPlotData:
    """巡回時間箱ひげ図データ"""

    stores: dict[str, BoxPlotStats]
    total: BoxPlotStats | None


@dataclass(frozen=True)
class CrawlTimeTimeseriesBoxPlotData:
    """巡回時間の時系列箱ひげ図データ（日単位）"""

    periods: list[str]  # YYYY-MM-DD
    total: dict[str, list[float]]  # period -> duration_sec のリスト
    stores: dict[str, dict[str, list[float]]]  # store_name -> period -> duration_sec のリスト


@dataclass(frozen=True)
class FailureTimeseriesData:
    """失敗数時系列データ"""

    labels: list[str]
    data: list[int]


class MetricsDB:
    """メトリクスデータベース管理クラス"""

    def __init__(self, db_path: pathlib.Path) -> None:
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self) -> None:
        """データベースとテーブルを作成"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        schema_sql = price_watch.const.SCHEMA_SQLITE_METRICS.read_text()
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(schema_sql)
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """データベース接続を取得"""
        return sqlite3.connect(self.db_path)

    # === セッション管理 ===

    def start_session(self) -> int:
        """新しい巡回セッションを開始

        Returns:
            セッションID
        """
        now = my_lib.time.now()
        now_str = now.isoformat()

        # 実行中のセッションがあれば強制終了
        self._close_orphan_sessions(now)

        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO crawl_sessions (started_at, last_heartbeat_at)
                VALUES (?, ?)
                """,
                (now_str, now_str),
            )
            session_id = cursor.lastrowid
            conn.commit()
            logging.info("Started crawl session %d", session_id)
            return session_id if session_id else 0

    def _close_orphan_sessions(self, now: datetime) -> None:
        """孤児セッション（ended_at が NULL）を強制終了"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT id, started_at FROM crawl_sessions
                WHERE ended_at IS NULL
                """
            )
            for row in cursor.fetchall():
                session_id, started_at_str = row
                started_at = datetime.fromisoformat(started_at_str)
                duration = (now - started_at).total_seconds()
                conn.execute(
                    """
                    UPDATE crawl_sessions
                    SET ended_at = ?, work_ended_at = ?, duration_sec = ?, exit_reason = ?
                    WHERE id = ?
                    """,
                    (now.isoformat(), now.isoformat(), duration, "superseded", session_id),
                )
                logging.warning("Closed orphan session %d (superseded)", session_id)
            conn.commit()

    def update_heartbeat(
        self,
        session_id: int,
        total_items: int | None = None,
        success_items: int | None = None,
        failed_items: int | None = None,
    ) -> None:
        """セッションのハートビートを更新.

        Args:
            session_id: セッションID
            total_items: 合計アイテム数（Noneの場合は更新しない）
            success_items: 成功アイテム数（Noneの場合は更新しない）
            failed_items: 失敗アイテム数（Noneの場合は更新しない）
        """
        now_str = my_lib.time.now().isoformat()
        with self._get_conn() as conn:
            if total_items is not None and success_items is not None and failed_items is not None:
                conn.execute(
                    """
                    UPDATE crawl_sessions
                    SET last_heartbeat_at = ?,
                        total_items = ?, success_items = ?, failed_items = ?
                    WHERE id = ?
                    """,
                    (now_str, total_items, success_items, failed_items, session_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE crawl_sessions
                    SET last_heartbeat_at = ?
                    WHERE id = ?
                    """,
                    (now_str, session_id),
                )
            conn.commit()

    def end_session(
        self,
        session_id: int,
        total_items: int,
        success_items: int,
        failed_items: int,
        exit_reason: str = "normal",
        work_ended_at: datetime | None = None,
    ) -> None:
        """巡回セッションを終了

        Args:
            session_id: セッションID
            total_items: 処理アイテム数
            success_items: 成功アイテム数
            failed_items: 失敗アイテム数
            exit_reason: 終了理由
            work_ended_at: 実際の作業終了時刻（スリープ時間を除外するため）
                           None の場合は現在時刻を使用
        """
        now = my_lib.time.now()
        work_ended = work_ended_at if work_ended_at is not None else now

        with self._get_conn() as conn:
            # 開始時刻を取得して duration を計算
            cursor = conn.execute(
                "SELECT started_at FROM crawl_sessions WHERE id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            started_at = datetime.fromisoformat(row[0]) if row else now
            duration = (work_ended - started_at).total_seconds()

            conn.execute(
                """
                UPDATE crawl_sessions
                SET ended_at = ?, work_ended_at = ?, last_heartbeat_at = ?,
                    duration_sec = ?,
                    total_items = ?, success_items = ?, failed_items = ?,
                    exit_reason = ?
                WHERE id = ?
                """,
                (
                    now.isoformat(),
                    work_ended.isoformat(),
                    now.isoformat(),
                    duration,
                    total_items,
                    success_items,
                    failed_items,
                    exit_reason,
                    session_id,
                ),
            )
            conn.commit()
            logging.info(
                "Ended crawl session %d: %d items (success=%d, failed=%d) in %.1fs",
                session_id,
                total_items,
                success_items,
                failed_items,
                duration,
            )

    def update_work_ended_at(self, session_id: int) -> None:
        """セッションの work_ended_at を現在時刻で即時更新（スリープ開始時に呼ぶ）."""
        now_str = my_lib.time.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE crawl_sessions
                SET work_ended_at = ?, last_heartbeat_at = ?
                WHERE id = ?
                """,
                (now_str, now_str, session_id),
            )
            conn.commit()

    def clear_work_ended_at(self, session_id: int) -> None:
        """セッションの work_ended_at を NULL にクリア（巡回再開時に呼ぶ）."""
        now_str = my_lib.time.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE crawl_sessions
                SET work_ended_at = NULL, last_heartbeat_at = ?
                WHERE id = ?
                """,
                (now_str, session_id),
            )
            conn.commit()

    # === ストア統計 ===

    def start_store_crawl(self, session_id: int, store_name: str) -> int:
        """ストアの巡回を開始

        Returns:
            ストア統計ID
        """
        now_str = my_lib.time.now().isoformat()
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO store_crawl_stats (session_id, store_name, started_at)
                VALUES (?, ?, ?)
                """,
                (session_id, store_name, now_str),
            )
            stats_id = cursor.lastrowid
            conn.commit()
            return stats_id if stats_id else 0

    def end_store_crawl(
        self,
        stats_id: int,
        item_count: int,
        success_count: int,
        failed_count: int,
    ) -> None:
        """ストアの巡回を終了"""
        now = my_lib.time.now()
        now_str = now.isoformat()

        with self._get_conn() as conn:
            # 開始時刻を取得
            cursor = conn.execute(
                "SELECT started_at FROM store_crawl_stats WHERE id = ?",
                (stats_id,),
            )
            row = cursor.fetchone()
            if row:
                started_at = datetime.fromisoformat(row[0])
                duration = (now - started_at).total_seconds()
            else:
                duration = 0

            conn.execute(
                """
                UPDATE store_crawl_stats
                SET ended_at = ?, duration_sec = ?,
                    item_count = ?, success_count = ?, failed_count = ?
                WHERE id = ?
                """,
                (now_str, duration, item_count, success_count, failed_count, stats_id),
            )
            conn.commit()

    # === クエリ ===

    def get_current_session_status(self) -> CurrentSessionStatus:
        """現在のセッション状態を取得

        巡回中/スリープ中の判定:
        - ended_at IS NULL かつ work_ended_at IS NULL → 巡回中
        - ended_at IS NULL かつ work_ended_at IS NOT NULL → スリープ中
        """
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT id, started_at, last_heartbeat_at, work_ended_at,
                       total_items, success_items, failed_items
                FROM crawl_sessions
                WHERE ended_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if row is None:
                return CurrentSessionStatus(
                    is_running=False,
                    is_crawling=False,
                    session_id=None,
                    started_at=None,
                    last_heartbeat_at=None,
                    uptime_sec=None,
                    total_items=0,
                    success_items=0,
                    failed_items=0,
                )

            session_id, started_at_str, heartbeat_str, work_ended_at_str, total, success, failed = row
            started_at = datetime.fromisoformat(started_at_str)
            last_heartbeat = datetime.fromisoformat(heartbeat_str) if heartbeat_str else None
            now = my_lib.time.now()
            uptime = (now - started_at).total_seconds()

            # work_ended_at が NULL → 巡回中、NOT NULL → スリープ中
            is_crawling = work_ended_at_str is None

            return CurrentSessionStatus(
                is_running=True,
                is_crawling=is_crawling,
                session_id=session_id,
                started_at=started_at,
                last_heartbeat_at=last_heartbeat,
                uptime_sec=uptime,
                total_items=total,
                success_items=success,
                failed_items=failed,
            )

    def get_sessions(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
    ) -> list[SessionInfo]:
        """セッション一覧を取得"""
        query = "SELECT * FROM crawl_sessions WHERE 1=1"
        params: list[str | int] = []

        if start_date:
            query += " AND started_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND started_at <= ?"
            params.append(end_date + "T23:59:59")

        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        with self._get_conn() as conn:
            cursor = conn.execute(query, params)
            # カラム順: id, started_at, last_heartbeat_at, ended_at, work_ended_at,
            #           duration_sec, total_items, success_items, failed_items, exit_reason
            return [
                SessionInfo(
                    id=row[0],
                    started_at=datetime.fromisoformat(row[1]),
                    last_heartbeat_at=datetime.fromisoformat(row[2]) if row[2] else None,
                    ended_at=datetime.fromisoformat(row[3]) if row[3] else None,
                    work_ended_at=datetime.fromisoformat(row[4]) if row[4] else None,
                    duration_sec=row[5],
                    total_items=row[6] or 0,
                    success_items=row[7] or 0,
                    failed_items=row[8] or 0,
                    exit_reason=row[9],
                )
                for row in cursor.fetchall()
            ]

    def get_store_stats(
        self,
        store_name: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 1000,
    ) -> list[StoreStats]:
        """ストア統計一覧を取得"""
        query = "SELECT * FROM store_crawl_stats WHERE 1=1"
        params: list[str | int] = []

        if store_name:
            query += " AND store_name = ?"
            params.append(store_name)
        if start_date:
            query += " AND started_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND started_at <= ?"
            params.append(end_date + "T23:59:59")

        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        with self._get_conn() as conn:
            cursor = conn.execute(query, params)
            return [
                StoreStats(
                    id=row[0],
                    session_id=row[1],
                    store_name=row[2],
                    started_at=datetime.fromisoformat(row[3]),
                    ended_at=datetime.fromisoformat(row[4]) if row[4] else None,
                    duration_sec=row[5],
                    item_count=row[6] or 0,
                    success_count=row[7] or 0,
                    failed_count=row[8] or 0,
                )
                for row in cursor.fetchall()
            ]

    def get_uptime_heatmap(self, start_date: str, end_date: str) -> HeatmapData:
        """稼働率ヒートマップを計算

        各日・各時間帯(0-23時)の稼働率を計算します。

        Args:
            start_date: 開始日 (YYYY-MM-DD)
            end_date: 終了日 (YYYY-MM-DD)

        Returns:
            HeatmapData
        """
        # 日付リストを生成
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
        dates: list[str] = []
        current = start_dt
        while current <= end_dt:
            dates.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)

        hours = list(range(24))

        # セッション一覧を取得
        sessions = self._get_session_intervals(start_date, end_date)

        now = my_lib.time.now()
        cells: list[HeatmapCell] = []

        for date_str in dates:
            date_dt = datetime.fromisoformat(date_str)
            # タイムゾーンを now と揃える
            if now.tzinfo:
                date_dt = date_dt.replace(tzinfo=now.tzinfo)

            for hour in hours:
                slot_start = date_dt.replace(hour=hour, minute=0, second=0, microsecond=0)
                slot_end = slot_start + timedelta(hours=1)

                # 未来のスロットはスキップ
                if slot_start > now:
                    continue

                # 進行中のスロットは現在時刻までで計算
                if slot_end > now:
                    slot_end = now

                # このスロット内の稼働時間を計算
                uptime = self._calculate_uptime_in_slot(sessions, slot_start, slot_end)
                slot_duration = (slot_end - slot_start).total_seconds()
                uptime_rate = uptime / slot_duration if slot_duration > 0 else 0.0

                cells.append(HeatmapCell(date=date_str, hour=hour, uptime_rate=uptime_rate))

        return HeatmapData(dates=dates, hours=hours, cells=cells)

    def _get_session_intervals(self, start_date: str, end_date: str) -> list[tuple[datetime, datetime]]:
        """指定期間内のセッション区間を取得"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT started_at, ended_at, last_heartbeat_at
                FROM crawl_sessions
                WHERE started_at <= ? AND (ended_at >= ? OR ended_at IS NULL)
                ORDER BY started_at
                """,
                (end_date + "T23:59:59", start_date),
            )
            intervals: list[tuple[datetime, datetime]] = []
            now = my_lib.time.now()

            for row in cursor.fetchall():
                started_at = datetime.fromisoformat(row[0])
                if now.tzinfo:
                    started_at = started_at.replace(tzinfo=now.tzinfo)

                if row[1]:  # ended_at がある
                    ended_at = datetime.fromisoformat(row[1])
                    if now.tzinfo:
                        ended_at = ended_at.replace(tzinfo=now.tzinfo)
                elif row[2]:  # last_heartbeat_at を使用
                    ended_at = datetime.fromisoformat(row[2])
                    if now.tzinfo:
                        ended_at = ended_at.replace(tzinfo=now.tzinfo)
                else:
                    ended_at = now

                intervals.append((started_at, ended_at))

            return intervals

    def _calculate_uptime_in_slot(
        self,
        sessions: list[tuple[datetime, datetime]],
        slot_start: datetime,
        slot_end: datetime,
    ) -> float:
        """スロット内の稼働時間（秒）を計算"""
        total_uptime = 0.0

        for session_start, session_end in sessions:
            # セッションとスロットの重なりを計算
            overlap_start = max(session_start, slot_start)
            overlap_end = min(session_end, slot_end)

            if overlap_start < overlap_end:
                total_uptime += (overlap_end - overlap_start).total_seconds()

        # 最大でスロット長を超えない
        slot_duration = (slot_end - slot_start).total_seconds()
        return min(total_uptime, slot_duration)

    @staticmethod
    def _compute_boxplot_stats(values: list[float]) -> BoxPlotStats | None:
        """箱ひげ図統計を計算"""
        if not values:
            return None

        sorted_values = sorted(values)
        count = len(sorted_values)
        min_val = sorted_values[0]
        max_val = sorted_values[-1]

        if count == 1:
            return BoxPlotStats(min=min_val, q1=min_val, median=min_val, q3=min_val, max=max_val, count=count)

        median_val = statistics.median(sorted_values)

        if count == 2:
            q1 = min_val
            q3 = max_val
        else:
            quantiles = statistics.quantiles(sorted_values, n=4)
            q1 = quantiles[0]
            q3 = quantiles[2]

        # IQR法で外れ値検出
        iqr = q3 - q1
        lower_fence = q1 - 1.5 * iqr
        upper_fence = q3 + 1.5 * iqr
        outliers = [v for v in sorted_values if v < lower_fence or v > upper_fence]

        # ひげの範囲（外れ値を除いた min/max）
        whisker_min = min((v for v in sorted_values if v >= lower_fence), default=min_val)
        whisker_max = max((v for v in sorted_values if v <= upper_fence), default=max_val)

        return BoxPlotStats(
            min=whisker_min,
            q1=q1,
            median=median_val,
            q3=q3,
            max=whisker_max,
            count=count,
            outliers=outliers,
        )

    def get_crawl_time_boxplot(self, days: int = 7) -> CrawlTimeBoxPlotData:
        """巡回時間の箱ひげ図データを取得

        Args:
            days: 集計期間（日数）

        Returns:
            CrawlTimeBoxPlotData
        """
        now = my_lib.time.now()
        since = (now - timedelta(days=days)).isoformat()

        with self._get_conn() as conn:
            # ストア別巡回時間
            cursor = conn.execute(
                """
                SELECT store_name, duration_sec
                FROM store_crawl_stats
                WHERE started_at >= ? AND duration_sec IS NOT NULL
                ORDER BY store_name
                """,
                (since,),
            )

            store_values: dict[str, list[float]] = {}
            for row in cursor.fetchall():
                store_name, duration = row
                if store_name not in store_values:
                    store_values[store_name] = []
                store_values[store_name].append(float(duration))

            stores: dict[str, BoxPlotStats] = {}
            for store_name, values in store_values.items():
                stats = self._compute_boxplot_stats(values)
                if stats:
                    stores[store_name] = stats

            # セッション全体の巡回時間（sleep 除外 = duration_sec）
            cursor = conn.execute(
                """
                SELECT duration_sec
                FROM crawl_sessions
                WHERE started_at >= ? AND duration_sec IS NOT NULL AND ended_at IS NOT NULL
                """,
                (since,),
            )
            total_values = [float(row[0]) for row in cursor.fetchall()]
            total = self._compute_boxplot_stats(total_values)

        return CrawlTimeBoxPlotData(stores=stores, total=total)

    def get_crawl_time_timeseries_boxplot(self, days: int = 7) -> CrawlTimeTimeseriesBoxPlotData:
        """巡回時間の時系列箱ひげ図データを取得（日単位）

        Args:
            days: 集計期間（日数）

        Returns:
            CrawlTimeTimeseriesBoxPlotData
        """
        now = my_lib.time.now()
        since = now - timedelta(days=days)
        since_str = since.isoformat()

        # 日付リストを生成
        periods: list[str] = []
        current = since.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        while current <= end:
            periods.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)

        with self._get_conn() as conn:
            # セッション全体の巡回時間（日別）
            cursor = conn.execute(
                """
                SELECT started_at, duration_sec
                FROM crawl_sessions
                WHERE started_at >= ? AND duration_sec IS NOT NULL AND ended_at IS NOT NULL
                """,
                (since_str,),
            )
            total_by_day: dict[str, list[float]] = {p: [] for p in periods}
            for row in cursor.fetchall():
                dt = datetime.fromisoformat(row[0])
                day_key = dt.strftime("%Y-%m-%d")
                if day_key in total_by_day:
                    total_by_day[day_key].append(float(row[1]))

            # ストア別巡回時間（日別）
            cursor = conn.execute(
                """
                SELECT store_name, started_at, duration_sec
                FROM store_crawl_stats
                WHERE started_at >= ? AND duration_sec IS NOT NULL
                ORDER BY store_name
                """,
                (since_str,),
            )
            stores_by_day: dict[str, dict[str, list[float]]] = {}
            for row in cursor.fetchall():
                store_name, started_at_str, duration = row
                dt = datetime.fromisoformat(started_at_str)
                day_key = dt.strftime("%Y-%m-%d")
                if store_name not in stores_by_day:
                    stores_by_day[store_name] = {p: [] for p in periods}
                if day_key in stores_by_day[store_name]:
                    stores_by_day[store_name][day_key].append(float(duration))

        return CrawlTimeTimeseriesBoxPlotData(
            periods=periods,
            total=total_by_day,
            stores=stores_by_day,
        )

    def get_failure_timeseries(self, days: int = 7) -> FailureTimeseriesData:
        """失敗数時系列データを取得（1時間単位）

        Args:
            days: 集計期間（日数）

        Returns:
            FailureTimeseriesData
        """
        now = my_lib.time.now()
        since = now - timedelta(days=days)

        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT started_at, failed_count
                FROM store_crawl_stats
                WHERE started_at >= ? AND failed_count > 0
                """,
                (since.isoformat(),),
            )

            # 1時間バケットに集計
            hourly_failures: dict[str, int] = {}
            for row in cursor.fetchall():
                started_at_str, failed_count = row
                dt = datetime.fromisoformat(started_at_str)
                bucket = dt.strftime("%Y-%m-%d %H:00")
                hourly_failures[bucket] = hourly_failures.get(bucket, 0) + int(failed_count)

        # 全時間スロットを生成
        labels: list[str] = []
        data: list[int] = []
        current = since.replace(minute=0, second=0, microsecond=0)
        while current <= now:
            bucket = current.strftime("%Y-%m-%d %H:00")
            labels.append(bucket)
            data.append(hourly_failures.get(bucket, 0))
            current += timedelta(hours=1)

        return FailureTimeseriesData(labels=labels, data=data)

    def is_crawler_healthy(self, max_age_sec: int = 600) -> bool:
        """クローラが健全に動作しているかチェック

        Args:
            max_age_sec: ハートビートの最大経過時間（秒）

        Returns:
            健全なら True
        """
        status = self.get_current_session_status()
        if not status.is_running:
            return False

        if status.last_heartbeat_at is None:
            return False

        now = my_lib.time.now()
        # タイムゾーンを揃える
        last_heartbeat = status.last_heartbeat_at
        if now.tzinfo and last_heartbeat.tzinfo is None:
            last_heartbeat = last_heartbeat.replace(tzinfo=now.tzinfo)

        elapsed = (now - last_heartbeat).total_seconds()
        return elapsed <= max_age_sec
