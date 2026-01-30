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

        スキーマファイルからテーブルとインデックスを作成します。
        既存データベースの場合は、スキーママイグレーションも実行します。
        """
        if self._initialized:
            return

        # ディレクトリが存在しない場合は作成
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        schema_sql = price_watch.const.SCHEMA_SQLITE_HISTORY.read_text()
        with my_lib.sqlite_util.connect(self.db_path) as conn:
            conn.executescript(schema_sql)

        # スキーママイグレーション: events.url カラムの追加（既存DB対応）
        self._migrate_events_url_column()

        self._initialized = True

    def _migrate_events_url_column(self) -> None:
        """events テーブルに url カラムを追加（既存DB対応）."""
        if not self.column_exists("events", "url"):
            with my_lib.sqlite_util.connect(self.db_path) as conn:
                conn.execute("ALTER TABLE events ADD COLUMN url TEXT")
                conn.commit()

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
