#!/usr/bin/env python3
"""
巡回メトリクスの記録・取得

巡回セッション、ストアごとの統計、ヒートマップ用データを管理します。
"""

from __future__ import annotations

import logging
import pathlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

import my_lib.time

# スキーマバージョン（マイグレーション用）
SCHEMA_VERSION = 1

# テーブル作成SQL
_CREATE_TABLES_SQL = """
-- スキーマバージョン管理
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

-- 巡回セッション（一通りの巡回サイクル）
CREATE TABLE IF NOT EXISTS crawl_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    last_heartbeat_at TEXT,
    ended_at TEXT,
    duration_sec REAL,
    total_items INTEGER DEFAULT 0,
    success_items INTEGER DEFAULT 0,
    failed_items INTEGER DEFAULT 0,
    exit_reason TEXT
);

-- ストアごとの巡回統計
CREATE TABLE IF NOT EXISTS store_crawl_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    store_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_sec REAL,
    item_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES crawl_sessions(id)
);

-- インデックス
CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON crawl_sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_ended_at ON crawl_sessions(ended_at);
CREATE INDEX IF NOT EXISTS idx_store_stats_session ON store_crawl_stats(session_id);
CREATE INDEX IF NOT EXISTS idx_store_stats_store ON store_crawl_stats(store_name);
CREATE INDEX IF NOT EXISTS idx_store_stats_started ON store_crawl_stats(started_at);
"""


@dataclass(frozen=True)
class SessionInfo:
    """セッション情報"""

    id: int
    started_at: datetime
    last_heartbeat_at: datetime | None
    ended_at: datetime | None
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
    session_id: int | None
    started_at: datetime | None
    last_heartbeat_at: datetime | None
    uptime_sec: float | None
    total_items: int
    success_items: int
    failed_items: int


class MetricsDB:
    """メトリクスデータベース管理クラス"""

    def __init__(self, db_path: pathlib.Path) -> None:
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self) -> None:
        """データベースとテーブルを作成"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(_CREATE_TABLES_SQL)
            # スキーマバージョンを記録
            cursor = conn.execute("SELECT version FROM schema_version LIMIT 1")
            row = cursor.fetchone()
            if row is None:
                conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
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
                    SET ended_at = ?, duration_sec = ?, exit_reason = ?
                    WHERE id = ?
                    """,
                    (now.isoformat(), duration, "superseded", session_id),
                )
                logging.warning("Closed orphan session %d (superseded)", session_id)
            conn.commit()

    def update_heartbeat(self, session_id: int) -> None:
        """セッションのハートビートを更新"""
        now_str = my_lib.time.now().isoformat()
        with self._get_conn() as conn:
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
        # 作業終了時刻が指定されていればそれを使用（スリープ時間を除外）
        ended_at = work_ended_at if work_ended_at is not None else now
        ended_at_str = ended_at.isoformat()

        with self._get_conn() as conn:
            # 開始時刻を取得して duration を計算
            cursor = conn.execute(
                "SELECT started_at FROM crawl_sessions WHERE id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            if row:
                started_at = datetime.fromisoformat(row[0])
                duration = (ended_at - started_at).total_seconds()
            else:
                duration = 0

            conn.execute(
                """
                UPDATE crawl_sessions
                SET ended_at = ?, last_heartbeat_at = ?, duration_sec = ?,
                    total_items = ?, success_items = ?, failed_items = ?,
                    exit_reason = ?
                WHERE id = ?
                """,
                (
                    ended_at_str,
                    now.isoformat(),  # ハートビートは常に現在時刻
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
        """現在のセッション状態を取得"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT id, started_at, last_heartbeat_at,
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
                    session_id=None,
                    started_at=None,
                    last_heartbeat_at=None,
                    uptime_sec=None,
                    total_items=0,
                    success_items=0,
                    failed_items=0,
                )

            session_id, started_at_str, heartbeat_str, total, success, failed = row
            started_at = datetime.fromisoformat(started_at_str)
            last_heartbeat = datetime.fromisoformat(heartbeat_str) if heartbeat_str else None
            now = my_lib.time.now()
            uptime = (now - started_at).total_seconds()

            return CurrentSessionStatus(
                is_running=True,
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
            return [
                SessionInfo(
                    id=row[0],
                    started_at=datetime.fromisoformat(row[1]),
                    last_heartbeat_at=datetime.fromisoformat(row[2]) if row[2] else None,
                    ended_at=datetime.fromisoformat(row[3]) if row[3] else None,
                    duration_sec=row[4],
                    total_items=row[5] or 0,
                    success_items=row[6] or 0,
                    failed_items=row[7] or 0,
                    exit_reason=row[8],
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
