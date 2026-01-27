#!/usr/bin/env python3
"""履歴 DB 接続管理.

データベース接続とスキーマ管理を担当します。
"""

from __future__ import annotations

import pathlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import my_lib.sqlite_util

import price_watch.const

if TYPE_CHECKING:
    pass


def dict_factory(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    """SQLite 結果を辞書に変換."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


# テーブル定義 SQL
ITEMS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS items(
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_key        TEXT NOT NULL UNIQUE,
    url             TEXT,
    name            TEXT NOT NULL,
    store           TEXT NOT NULL,
    thumb_url       TEXT,
    search_keyword  TEXT,
    search_cond     TEXT,
    created_at      TIMESTAMP DEFAULT(DATETIME('now','localtime')),
    updated_at      TIMESTAMP DEFAULT(DATETIME('now','localtime'))
)
"""

PRICE_HISTORY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS price_history(
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id      INTEGER NOT NULL,
    price        INTEGER,
    stock        INTEGER,
    crawl_status INTEGER NOT NULL DEFAULT 1,
    time         TIMESTAMP DEFAULT(DATETIME('now','localtime')),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
)
"""

EVENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS events(
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id        INTEGER NOT NULL,
    event_type     TEXT NOT NULL,
    price          INTEGER,
    old_price      INTEGER,
    threshold_days INTEGER,
    created_at     TIMESTAMP DEFAULT(DATETIME('now','localtime')),
    notified       INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
)
"""

INDEX_SQLS = [
    "CREATE INDEX IF NOT EXISTS idx_items_item_key ON items(item_key)",
    "CREATE INDEX IF NOT EXISTS idx_price_history_item_id ON price_history(item_id)",
    "CREATE INDEX IF NOT EXISTS idx_price_history_time ON price_history(time)",
    # 複合インデックス: item_id + time でのクエリを高速化
    "CREATE INDEX IF NOT EXISTS idx_price_history_item_time ON price_history(item_id, time DESC)",
    "CREATE INDEX IF NOT EXISTS idx_events_item_id ON events(item_id)",
    "CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)",
]


@dataclass
class HistoryDBConnection:
    """履歴 DB 接続クラス.

    データベース接続とスキーマ管理を担当します。
    """

    db_path: pathlib.Path
    _initialized: bool = field(default=False, init=False)

    @classmethod
    def create(cls, data_path: pathlib.Path) -> HistoryDBConnection:
        """データパスから HistoryDBConnection を作成.

        Args:
            data_path: データディレクトリパス

        Returns:
            HistoryDBConnection インスタンス
        """
        db_path = data_path / price_watch.const.DB_FILE
        return cls(db_path=db_path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """データベースに接続.

        Yields:
            SQLite Connection
        """
        with my_lib.sqlite_util.connect(self.db_path) as conn:
            conn.row_factory = dict_factory  # type: ignore[assignment]
            yield conn

    def initialize(self) -> None:
        """データベースを初期化.

        テーブルとインデックスを作成します。
        """
        if self._initialized:
            return

        # ディレクトリが存在しない場合は作成
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with my_lib.sqlite_util.connect(self.db_path) as conn:
            cur = conn.cursor()

            # テーブル作成
            cur.execute(ITEMS_TABLE_SQL)
            cur.execute(PRICE_HISTORY_TABLE_SQL)
            cur.execute(EVENTS_TABLE_SQL)

        self._initialized = True

    def create_indexes(self) -> None:
        """インデックスを作成.

        マイグレーション後に呼び出します。
        """
        with my_lib.sqlite_util.connect(self.db_path) as conn:
            cur = conn.cursor()
            for sql in INDEX_SQLS:
                cur.execute(sql)

    def table_exists(self, table_name: str) -> bool:
        """テーブルが存在するか確認.

        Args:
            table_name: テーブル名

        Returns:
            存在する場合 True
        """
        with my_lib.sqlite_util.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            return cur.fetchone() is not None

    def column_exists(self, table_name: str, column_name: str) -> bool:
        """カラムが存在するか確認.

        Args:
            table_name: テーブル名
            column_name: カラム名

        Returns:
            存在する場合 True
        """
        with my_lib.sqlite_util.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cur.fetchall()]
            return column_name in columns
