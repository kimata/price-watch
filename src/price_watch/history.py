#!/usr/bin/env python3
"""価格履歴管理（SQLite）."""

from __future__ import annotations

import hashlib
import logging
import pathlib
import sqlite3
from typing import Any

import my_lib.time

import price_watch.const

# モジュールレベルのデータパス（init で設定される）
_data_path: pathlib.Path = price_watch.const.DATA_PATH


def _dict_factory(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    """SQLite 結果を辞書に変換."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def _connect() -> sqlite3.Connection:
    """データベースに接続."""
    _data_path.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_data_path / price_watch.const.DB_FILE))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _url_hash(url: str) -> str:
    """URLからハッシュを生成."""
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def _get_or_create_item(
    cur: sqlite3.Cursor, url: str, name: str, store: str, thumb_url: str | None = None
) -> int:
    """アイテムを取得または作成し、IDを返す."""
    url_hash = _url_hash(url)

    cur.execute("SELECT id, name, thumb_url FROM items WHERE url_hash = ?", (url_hash,))
    row = cur.fetchone()

    if row:
        item_id = row[0]
        # 名前やサムネイルが更新されていたら更新
        updates = []
        params: list[Any] = []
        if row[1] != name:
            updates.append("name = ?")
            params.append(name)
        if thumb_url and row[2] != thumb_url:
            updates.append("thumb_url = ?")
            params.append(thumb_url)
        if updates:
            updates.append("updated_at = ?")
            params.append(my_lib.time.now().strftime("%Y-%m-%d %H:%M:%S"))
            params.append(item_id)
            cur.execute(f"UPDATE items SET {', '.join(updates)} WHERE id = ?", params)  # noqa: S608
        return item_id

    # 新規作成
    now = my_lib.time.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        """
        INSERT INTO items (url_hash, url, name, store, thumb_url, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (url_hash, url, name, store, thumb_url, now, now),
    )
    return cur.lastrowid or 0


def insert(item: dict[str, Any]) -> None:
    """価格履歴を挿入."""
    conn = _connect()
    cur = conn.cursor()

    item_id = _get_or_create_item(
        cur,
        item["url"],
        item["name"],
        item["store"],
        item.get("thumb_url"),
    )

    cur.execute(
        """
        INSERT INTO price_history (item_id, price, stock)
        VALUES (?, ?, ?)
        """,
        (item_id, item["price"], item["stock"]),
    )

    conn.commit()
    conn.close()


def last(url: str) -> dict[str, Any] | None:
    """最新の価格履歴を取得."""
    conn = _connect()
    conn.row_factory = _dict_factory
    cur = conn.cursor()

    url_hash = _url_hash(url)
    cur.execute(
        """
        SELECT i.url, i.name, i.store, i.thumb_url, ph.price, ph.stock, ph.time
        FROM items i
        JOIN price_history ph ON i.id = ph.item_id
        WHERE i.url_hash = ?
        ORDER BY ph.time DESC
        LIMIT 1
        """,
        (url_hash,),
    )

    result = cur.fetchone()
    conn.close()

    return result


def lowest(url: str) -> dict[str, Any] | None:
    """最安値の価格履歴を取得."""
    conn = _connect()
    conn.row_factory = _dict_factory
    cur = conn.cursor()

    url_hash = _url_hash(url)
    cur.execute(
        """
        SELECT i.url, i.name, i.store, i.thumb_url, ph.price, ph.stock, ph.time
        FROM items i
        JOIN price_history ph ON i.id = ph.item_id
        WHERE i.url_hash = ?
        ORDER BY ph.price ASC
        LIMIT 1
        """,
        (url_hash,),
    )

    result = cur.fetchone()
    conn.close()

    return result


def get_all_items() -> list[dict[str, Any]]:
    """全アイテムを取得."""
    conn = _connect()
    conn.row_factory = _dict_factory
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, url_hash, url, name, store, thumb_url, created_at, updated_at
        FROM items
        ORDER BY updated_at DESC
        """
    )

    items = cur.fetchall()
    conn.close()

    return items


def get_item_history(
    url_hash: str, days: int | None = None
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """アイテムの価格履歴を取得."""
    conn = _connect()
    conn.row_factory = _dict_factory
    cur = conn.cursor()

    # アイテム情報を取得
    cur.execute(
        """
        SELECT id, url_hash, url, name, store, thumb_url, created_at, updated_at
        FROM items
        WHERE url_hash = ?
        """,
        (url_hash,),
    )
    item = cur.fetchone()

    if not item:
        conn.close()
        return None, []

    # 価格履歴を取得
    if days and days > 0:
        cur.execute(
            """
            SELECT price, stock, time
            FROM price_history
            WHERE item_id = ?
              AND time >= datetime('now', 'localtime', ?)
            ORDER BY time ASC
            """,
            (item["id"], f"-{days} days"),
        )
    else:
        cur.execute(
            """
            SELECT price, stock, time
            FROM price_history
            WHERE item_id = ?
            ORDER BY time ASC
            """,
            (item["id"],),
        )

    history = cur.fetchall()
    conn.close()

    return item, history


def get_item_stats(item_id: int, days: int | None = None) -> dict[str, Any]:
    """アイテムの統計情報を取得."""
    conn = _connect()
    conn.row_factory = _dict_factory
    cur = conn.cursor()

    if days and days > 0:
        cur.execute(
            """
            SELECT
                MIN(price) as lowest_price,
                MAX(price) as highest_price,
                COUNT(*) as data_count
            FROM price_history
            WHERE item_id = ?
              AND time >= datetime('now', 'localtime', ?)
            """,
            (item_id, f"-{days} days"),
        )
    else:
        cur.execute(
            """
            SELECT
                MIN(price) as lowest_price,
                MAX(price) as highest_price,
                COUNT(*) as data_count
            FROM price_history
            WHERE item_id = ?
            """,
            (item_id,),
        )

    stats = cur.fetchone()
    conn.close()

    return stats or {"lowest_price": None, "highest_price": None, "data_count": 0}


def get_latest_price(item_id: int) -> dict[str, Any] | None:
    """アイテムの最新価格を取得."""
    conn = _connect()
    conn.row_factory = _dict_factory
    cur = conn.cursor()

    cur.execute(
        """
        SELECT price, stock, time
        FROM price_history
        WHERE item_id = ?
        ORDER BY time DESC
        LIMIT 1
        """,
        (item_id,),
    )

    result = cur.fetchone()
    conn.close()

    return result


def init(data_path: pathlib.Path | None = None) -> None:
    """データベースを初期化.

    Args:
        data_path: データを保存するディレクトリのパス。省略時はデフォルトを使用。
    """
    global _data_path
    if data_path is not None:
        _data_path = data_path

    conn = _connect()
    cur = conn.cursor()

    # items テーブル
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS items(
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash    TEXT NOT NULL UNIQUE,
            url         TEXT NOT NULL,
            name        TEXT NOT NULL,
            store       TEXT NOT NULL,
            thumb_url   TEXT,
            created_at  TIMESTAMP DEFAULT(DATETIME('now','localtime')),
            updated_at  TIMESTAMP DEFAULT(DATETIME('now','localtime'))
        )
        """
    )

    # price_history テーブル
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history(
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            price   INTEGER NOT NULL,
            stock   INTEGER NOT NULL,
            time    TIMESTAMP DEFAULT(DATETIME('now','localtime')),
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
        )
        """
    )

    # インデックス
    cur.execute("CREATE INDEX IF NOT EXISTS idx_items_url_hash ON items(url_hash)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_item_id ON price_history(item_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_time ON price_history(time)")

    conn.commit()
    conn.close()


def migrate_from_old_schema() -> None:
    """旧スキーマからデータをマイグレーション."""
    conn = _connect()
    cur = conn.cursor()

    # 旧テーブルが存在するか確認
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'")
    if not cur.fetchone():
        logging.info("No old price_history table found")
        conn.close()
        return

    # 旧テーブルの構造を確認（url カラムがあるかどうか）
    cur.execute("PRAGMA table_info(price_history)")
    columns = [row[1] for row in cur.fetchall()]

    if "url" not in columns:
        logging.info("Already migrated or new schema")
        conn.close()
        return

    logging.info("Starting migration from old schema...")

    # 新しいテーブルを作成
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS items(
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash    TEXT NOT NULL UNIQUE,
            url         TEXT NOT NULL,
            name        TEXT NOT NULL,
            store       TEXT NOT NULL,
            thumb_url   TEXT,
            created_at  TIMESTAMP DEFAULT(DATETIME('now','localtime')),
            updated_at  TIMESTAMP DEFAULT(DATETIME('now','localtime'))
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history_new(
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            price   INTEGER NOT NULL,
            stock   INTEGER NOT NULL,
            time    TIMESTAMP DEFAULT(DATETIME('now','localtime')),
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
        )
        """
    )

    # 旧データからユニークなアイテムを抽出してitemsテーブルに挿入
    cur.execute(
        """
        SELECT DISTINCT url, name, store
        FROM price_history
        """
    )
    unique_items = cur.fetchall()

    item_id_map: dict[str, int] = {}
    for url, name, store in unique_items:
        url_hash = _url_hash(url)
        cur.execute(
            """
            INSERT OR IGNORE INTO items (url_hash, url, name, store)
            VALUES (?, ?, ?, ?)
            """,
            (url_hash, url, name, store),
        )
        cur.execute("SELECT id FROM items WHERE url_hash = ?", (url_hash,))
        item_id_map[url] = cur.fetchone()[0]

    # 価格履歴を新テーブルに移行
    cur.execute("SELECT url, price, stock, time FROM price_history")
    for url, price, stock, time in cur.fetchall():
        item_id = item_id_map.get(url)
        if item_id:
            cur.execute(
                """
                INSERT INTO price_history_new (item_id, price, stock, time)
                VALUES (?, ?, ?, ?)
                """,
                (item_id, price, stock, time),
            )

    # 旧テーブルを削除し、新テーブルをリネーム
    cur.execute("DROP TABLE price_history")
    cur.execute("ALTER TABLE price_history_new RENAME TO price_history")

    # インデックスを作成
    cur.execute("CREATE INDEX IF NOT EXISTS idx_items_url_hash ON items(url_hash)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_item_id ON price_history(item_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_time ON price_history(time)")

    conn.commit()
    conn.close()

    logging.info("Migration completed successfully")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        logging.basicConfig(level=logging.INFO)
        migrate_from_old_schema()
    else:
        init()
