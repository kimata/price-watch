#!/usr/bin/env python3
"""価格履歴管理（SQLite）."""

from __future__ import annotations

import hashlib
import logging
import pathlib
import sqlite3
from typing import Any

import my_lib.sqlite_util
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


def _get_db_path() -> pathlib.Path:
    """データベースファイルのパスを取得."""
    return _data_path / price_watch.const.DB_FILE


def _url_hash(url: str) -> str:
    """URLからハッシュを生成."""
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def url_hash(url: str) -> str:
    """URLからハッシュを生成（公開API）."""
    return _url_hash(url)


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


def insert(item: dict[str, Any], *, crawl_status: int = 1) -> int:
    """価格履歴を挿入または更新.

    1時間に1回の記録を保持する。同一時間帯で複数回取得した場合:
    - より安い価格で更新（価格がある場合のみ）
    - 収集時刻は常に最新に更新

    データモデル:
    - crawl_status=0: クロール失敗 → stock=NULL, price=NULL
    - crawl_status=1, stock=0: 在庫なし → price=NULL
    - crawl_status=1, stock=1: 在庫あり → price=有効な価格

    Args:
        item: アイテム情報
        crawl_status: クロール状態（0: 失敗, 1: 成功）

    Returns:
        アイテムID
    """
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        cur = conn.cursor()

        item_id = _get_or_create_item(
            cur,
            item["url"],
            item["name"],
            item["store"],
            item.get("thumb_url"),
        )

        now = my_lib.time.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        # 現在時刻の「時」の開始時刻（例: 14:35 → 14:00:00）
        hour_start = now.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")

        # crawl_status=0 の場合は stock=NULL, price=NULL
        if crawl_status == 0:
            new_stock: int | None = None
            new_price: int | None = None
        else:
            new_stock = item.get("stock", 0)
            new_price = item.get("price")  # 在庫なしの場合は None

        # 同一時間帯の既存レコードを確認
        cur.execute(
            """
            SELECT id, price, stock, crawl_status
            FROM price_history
            WHERE item_id = ?
              AND time >= ?
            ORDER BY time DESC
            LIMIT 1
            """,
            (item_id, hour_start),
        )
        existing = cur.fetchone()

        if existing:
            existing_id, existing_price, existing_stock, existing_crawl_status = existing

            # 更新判定
            should_update = False
            final_price = new_price
            final_stock = new_stock

            # クロール成功時のロジック
            if crawl_status == 1:
                if existing_crawl_status == 0:
                    # 失敗→成功: 新しいデータで上書き
                    should_update = True
                elif new_price is not None and existing_price is not None:
                    # 両方価格がある場合: より安い価格を採用（在庫ありの場合のみ）
                    if new_stock == 1:
                        final_price = min(new_price, existing_price)
                        should_update = new_price < existing_price
                    else:
                        should_update = True
                elif new_price is not None and existing_price is None:
                    # 新しく価格が取得できた場合
                    should_update = True
                elif new_stock != existing_stock:
                    # 在庫状態が変わった場合
                    should_update = True
            else:
                # クロール失敗時
                if existing_crawl_status == 1:
                    # 成功→失敗: 既存のデータを維持、crawl_status のみ更新
                    final_price = existing_price
                    final_stock = existing_stock
                    should_update = True
                # 失敗→失敗: 時刻のみ更新

            if should_update:
                cur.execute(
                    """
                    UPDATE price_history
                    SET price = ?, stock = ?, crawl_status = ?, time = ?
                    WHERE id = ?
                    """,
                    (final_price, final_stock, crawl_status, now_str, existing_id),
                )
            else:
                # 時刻だけは更新
                cur.execute(
                    """
                    UPDATE price_history
                    SET time = ?
                    WHERE id = ?
                    """,
                    (now_str, existing_id),
                )
        else:
            # 新規挿入
            cur.execute(
                """
                INSERT INTO price_history (item_id, price, stock, crawl_status, time)
                VALUES (?, ?, ?, ?, ?)
                """,
                (item_id, new_price, new_stock, crawl_status, now_str),
            )

        return item_id


def last(url: str) -> dict[str, Any] | None:
    """最新の価格履歴を取得."""
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        conn.row_factory = _dict_factory  # type: ignore[assignment]
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

        return cur.fetchone()


def lowest(url: str) -> dict[str, Any] | None:
    """最安値の価格履歴を取得（価格がNULLのレコードは除外）."""
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        conn.row_factory = _dict_factory  # type: ignore[assignment]
        cur = conn.cursor()

        url_hash = _url_hash(url)
        cur.execute(
            """
            SELECT i.url, i.name, i.store, i.thumb_url, ph.price, ph.stock, ph.time
            FROM items i
            JOIN price_history ph ON i.id = ph.item_id
            WHERE i.url_hash = ? AND ph.price IS NOT NULL
            ORDER BY ph.price ASC
            LIMIT 1
            """,
            (url_hash,),
        )

        return cur.fetchone()


def get_all_items() -> list[dict[str, Any]]:
    """全アイテムを取得."""
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        conn.row_factory = _dict_factory  # type: ignore[assignment]
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, url_hash, url, name, store, thumb_url, created_at, updated_at
            FROM items
            ORDER BY updated_at DESC
            """
        )

        return cur.fetchall()


def get_item_history(
    url_hash: str, days: int | None = None
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """アイテムの価格履歴を取得."""
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        conn.row_factory = _dict_factory  # type: ignore[assignment]
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

        return item, cur.fetchall()


def get_item_stats(item_id: int, days: int | None = None) -> dict[str, Any]:
    """アイテムの統計情報を取得（価格がNULLのレコードは除外）."""
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        conn.row_factory = _dict_factory  # type: ignore[assignment]
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
                  AND price IS NOT NULL
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
                  AND price IS NOT NULL
                """,
                (item_id,),
            )

        stats = cur.fetchone()
        return stats or {"lowest_price": None, "highest_price": None, "data_count": 0}


def get_latest_price(item_id: int) -> dict[str, Any] | None:
    """アイテムの最新価格を取得."""
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        conn.row_factory = _dict_factory  # type: ignore[assignment]
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

        return cur.fetchone()


def init(data_path: pathlib.Path | None = None) -> None:
    """データベースを初期化.

    Args:
        data_path: データを保存するディレクトリのパス。省略時はデフォルトを使用。
    """
    global _data_path
    if data_path is not None:
        _data_path = data_path

    # ディレクトリが存在しない場合は作成
    _data_path.mkdir(parents=True, exist_ok=True)

    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
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
        # crawl_status: 0=失敗, 1=成功
        # stock: NULL=不明（crawl_status=0時）, 0=在庫なし, 1=在庫あり
        # price: NULL=取得不可/在庫なし, INTEGER=有効な価格（crawl_status=1 AND stock=1 時のみ）
        cur.execute(
            """
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
        )

        # events テーブル（イベント記録用）
        # メッセージは保存せず、パラメータのみを保存
        cur.execute(
            """
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
        )

        # インデックス
        cur.execute("CREATE INDEX IF NOT EXISTS idx_items_url_hash ON items(url_hash)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_item_id ON price_history(item_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_time ON price_history(time)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_item_id ON events(item_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")

    # 既存DBのマイグレーション
    migrate_to_nullable_price()
    migrate_add_crawl_status()


def migrate_from_old_schema() -> None:
    """旧スキーマからデータをマイグレーション."""
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        cur = conn.cursor()

        # 旧テーブルが存在するか確認
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'")
        if not cur.fetchone():
            logging.info("No old price_history table found")
            return

        # 旧テーブルの構造を確認（url カラムがあるかどうか）
        cur.execute("PRAGMA table_info(price_history)")
        columns = [row[1] for row in cur.fetchall()]

        if "url" not in columns:
            logging.info("Already migrated or new schema")
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
        for url, price, stock, time_val in cur.fetchall():
            item_id = item_id_map.get(url)
            if item_id:
                cur.execute(
                    """
                    INSERT INTO price_history_new (item_id, price, stock, time)
                    VALUES (?, ?, ?, ?)
                    """,
                    (item_id, price, stock, time_val),
                )

        # 旧テーブルを削除し、新テーブルをリネーム
        cur.execute("DROP TABLE price_history")
        cur.execute("ALTER TABLE price_history_new RENAME TO price_history")

        # インデックスを作成
        cur.execute("CREATE INDEX IF NOT EXISTS idx_items_url_hash ON items(url_hash)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_item_id ON price_history(item_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_time ON price_history(time)")

    logging.info("Migration completed successfully")


def migrate_to_nullable_price() -> None:
    """price カラムを NULL 許可に変更するマイグレーション.

    SQLite は ALTER COLUMN をサポートしていないため、
    テーブルを再作成してデータを移行する。
    """
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        cur = conn.cursor()

        # テーブルが存在するか確認
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'")
        if not cur.fetchone():
            logging.info("No price_history table found")
            return

        # 現在のスキーマを確認（price カラムが NOT NULL かどうか）
        cur.execute("PRAGMA table_info(price_history)")
        columns = cur.fetchall()
        price_col = next((col for col in columns if col[1] == "price"), None)

        if price_col is None:
            logging.info("price column not found")
            return

        # notnull フラグ: 1 = NOT NULL, 0 = NULL 許可
        if price_col[3] == 0:
            logging.info("price column already allows NULL")
            return

        logging.info("Starting migration to allow NULL in price column...")

        # 新しいテーブルを作成（price に NULL を許可）
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS price_history_new(
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                price   INTEGER,
                stock   INTEGER NOT NULL,
                time    TIMESTAMP DEFAULT(DATETIME('now','localtime')),
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            )
            """
        )

        # データを移行
        cur.execute(
            """
            INSERT INTO price_history_new (id, item_id, price, stock, time)
            SELECT id, item_id, price, stock, time FROM price_history
            """
        )

        # 旧テーブルを削除し、新テーブルをリネーム
        cur.execute("DROP TABLE price_history")
        cur.execute("ALTER TABLE price_history_new RENAME TO price_history")

        # インデックスを再作成
        cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_item_id ON price_history(item_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_time ON price_history(time)")

    logging.info("Migration to nullable price completed successfully")


def migrate_add_crawl_status() -> None:
    """crawl_status カラムを追加するマイグレーション."""
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        cur = conn.cursor()

        # テーブルが存在するか確認
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'")
        if not cur.fetchone():
            logging.info("No price_history table found")
            return

        # 現在のスキーマを確認（crawl_status カラムが存在するか）
        cur.execute("PRAGMA table_info(price_history)")
        columns = [col[1] for col in cur.fetchall()]

        if "crawl_status" in columns:
            logging.info("crawl_status column already exists")
            return

        logging.info("Adding crawl_status column to price_history...")

        # カラムを追加（デフォルト値 1 = 成功）
        cur.execute("ALTER TABLE price_history ADD COLUMN crawl_status INTEGER NOT NULL DEFAULT 1")

    logging.info("Migration to add crawl_status completed successfully")


def get_item_id(url: str) -> int | None:
    """URL からアイテム ID を取得."""
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        cur = conn.cursor()
        url_hash = _url_hash(url)
        cur.execute("SELECT id FROM items WHERE url_hash = ?", (url_hash,))
        row = cur.fetchone()
        return row[0] if row else None


def get_item_by_id(item_id: int) -> dict[str, Any] | None:
    """アイテム ID からアイテム情報を取得."""
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        conn.row_factory = _dict_factory  # type: ignore[assignment]
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, url_hash, url, name, store, thumb_url, created_at, updated_at
            FROM items
            WHERE id = ?
            """,
            (item_id,),
        )
        return cur.fetchone()


def get_lowest_price_in_period(item_id: int, days: int | None = None) -> int | None:
    """指定期間内の最安値を取得.

    Args:
        item_id: アイテム ID
        days: 期間（日数）。None の場合は全期間。

    Returns:
        最安値。レコードがない場合は None。
    """
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        cur = conn.cursor()

        if days and days > 0:
            cur.execute(
                """
                SELECT MIN(price)
                FROM price_history
                WHERE item_id = ?
                  AND time >= datetime('now', 'localtime', ?)
                  AND price IS NOT NULL
                  AND crawl_status = 1
                """,
                (item_id, f"-{days} days"),
            )
        else:
            cur.execute(
                """
                SELECT MIN(price)
                FROM price_history
                WHERE item_id = ?
                  AND price IS NOT NULL
                  AND crawl_status = 1
                """,
                (item_id,),
            )

        row = cur.fetchone()
        return row[0] if row and row[0] is not None else None


def has_successful_crawl_in_hours(item_id: int, hours: int) -> bool:
    """指定時間内に成功したクロールがあるか確認.

    Args:
        item_id: アイテム ID
        hours: 確認する時間数

    Returns:
        成功したクロールがあれば True
    """
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM price_history
            WHERE item_id = ?
              AND time >= datetime('now', 'localtime', ?)
              AND crawl_status = 1
            """,
            (item_id, f"-{hours} hours"),
        )
        row = cur.fetchone()
        return row[0] > 0 if row else False


def get_last_successful_crawl(item_id: int) -> dict[str, Any] | None:
    """最後に成功したクロールを取得."""
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        conn.row_factory = _dict_factory  # type: ignore[assignment]
        cur = conn.cursor()
        cur.execute(
            """
            SELECT price, stock, crawl_status, time
            FROM price_history
            WHERE item_id = ?
              AND crawl_status = 1
            ORDER BY time DESC
            LIMIT 1
            """,
            (item_id,),
        )
        return cur.fetchone()


# --- イベント関連 ---


def insert_event(
    item_id: int,
    event_type: str,
    *,
    price: int | None = None,
    old_price: int | None = None,
    threshold_days: int | None = None,
    notified: bool = False,
) -> int:
    """イベントを記録.

    Args:
        item_id: アイテム ID
        event_type: イベントタイプ
        price: 現在価格
        old_price: 以前の価格
        threshold_days: 判定に使用した期間
        notified: 通知済みフラグ

    Returns:
        イベント ID
    """
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        cur = conn.cursor()
        now_str = my_lib.time.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            """
            INSERT INTO events (item_id, event_type, price, old_price, threshold_days, created_at, notified)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (item_id, event_type, price, old_price, threshold_days, now_str, 1 if notified else 0),
        )
        return cur.lastrowid or 0


def get_last_event(item_id: int, event_type: str) -> dict[str, Any] | None:
    """指定タイプの最新イベントを取得."""
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        conn.row_factory = _dict_factory  # type: ignore[assignment]
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, item_id, event_type, price, old_price, threshold_days, created_at, notified
            FROM events
            WHERE item_id = ? AND event_type = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (item_id, event_type),
        )
        return cur.fetchone()


def has_event_in_hours(item_id: int, event_type: str, hours: int) -> bool:
    """指定時間内に同じイベントが発生しているか確認."""
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM events
            WHERE item_id = ?
              AND event_type = ?
              AND created_at >= datetime('now', 'localtime', ?)
            """,
            (item_id, event_type, f"-{hours} hours"),
        )
        row = cur.fetchone()
        return row[0] > 0 if row else False


def get_recent_events(limit: int = 10) -> list[dict[str, Any]]:
    """最新のイベントを取得（アイテム情報付き）."""
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        conn.row_factory = _dict_factory  # type: ignore[assignment]
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                e.id,
                e.item_id,
                e.event_type,
                e.price,
                e.old_price,
                e.threshold_days,
                e.created_at,
                e.notified,
                i.name as item_name,
                i.store,
                i.url,
                i.thumb_url
            FROM events e
            JOIN items i ON e.item_id = i.id
            ORDER BY e.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cur.fetchall()


def mark_event_notified(event_id: int) -> None:
    """イベントを通知済みにする."""
    with my_lib.sqlite_util.connect(_get_db_path()) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE events SET notified = 1 WHERE id = ?", (event_id,))


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        logging.basicConfig(level=logging.INFO)
        migrate_from_old_schema()
    elif len(sys.argv) > 1 and sys.argv[1] == "migrate-nullable-price":
        logging.basicConfig(level=logging.INFO)
        migrate_to_nullable_price()
    else:
        init()
