#!/usr/bin/env python3
"""イベント Repository.

イベントの CRUD 操作を担当します。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import my_lib.time

import price_watch.models

if TYPE_CHECKING:
    from price_watch.managers.history.connection import HistoryDBConnection


@dataclass
class EventRepository:
    """イベント Repository.

    イベントの CRUD 操作を提供します。
    """

    db: HistoryDBConnection

    def insert(
        self,
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
        with self.db.connect() as conn:
            cur = conn.cursor()
            now_str = my_lib.time.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                """
                INSERT INTO events
                    (item_id, event_type, price, old_price, threshold_days, created_at, notified)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (item_id, event_type, price, old_price, threshold_days, now_str, 1 if notified else 0),
            )
            conn.commit()
            return cur.lastrowid or 0

    def get_last(self, item_id: int, event_type: str) -> price_watch.models.EventRecord | None:
        """指定タイプの最新イベントを取得.

        Args:
            item_id: アイテム ID
            event_type: イベントタイプ

        Returns:
            イベント情報、または None
        """
        with self.db.connect() as conn:
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
            row = cur.fetchone()
            return price_watch.models.EventRecord.from_dict(row) if row else None

    def has_event_in_hours(self, item_id: int, event_type: str, hours: int) -> bool:
        """指定時間内に同じイベントが発生しているか確認.

        Args:
            item_id: アイテム ID
            event_type: イベントタイプ
            hours: 確認する時間数

        Returns:
            イベントがあれば True
        """
        with self.db.connect() as conn:
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
            if row:
                values = list(row.values())
                return values[0] > 0 if values else False
            return False

    def get_recent(self, limit: int = 10) -> list[price_watch.models.EventRecord]:
        """最新のイベントを取得（アイテム情報付き）.

        サムネイル画像は、該当アイテムになければ同じ商品名の他のストアから取得する。

        Args:
            limit: 取得件数上限

        Returns:
            イベントのリスト（新しい順）
        """
        with self.db.connect() as conn:
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
                    COALESCE(
                        i.thumb_url,
                        (SELECT thumb_url FROM items WHERE name = i.name AND thumb_url IS NOT NULL LIMIT 1)
                    ) as thumb_url
                FROM events e
                JOIN items i ON e.item_id = i.id
                ORDER BY e.created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [price_watch.models.EventRecord.from_dict(row) for row in cur.fetchall()]

    def mark_notified(self, event_id: int) -> None:
        """イベントを通知済みにする.

        Args:
            event_id: イベント ID
        """
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE events SET notified = 1 WHERE id = ?", (event_id,))
            conn.commit()

    def get_by_item(self, item_key: str, limit: int = 50) -> list[price_watch.models.EventRecord]:
        """指定アイテムのイベント履歴を取得（アイテム情報付き）.

        サムネイル画像は、該当アイテムになければ同じ商品名の他のストアから取得する。

        Args:
            item_key: アイテムキー
            limit: 取得件数上限

        Returns:
            イベントのリスト（新しい順）
        """
        with self.db.connect() as conn:
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
                    COALESCE(
                        i.thumb_url,
                        (SELECT thumb_url FROM items WHERE name = i.name AND thumb_url IS NOT NULL LIMIT 1)
                    ) as thumb_url
                FROM events e
                JOIN items i ON e.item_id = i.id
                WHERE i.item_key = ?
                ORDER BY e.created_at DESC
                LIMIT ?
                """,
                (item_key, limit),
            )
            return [price_watch.models.EventRecord.from_dict(row) for row in cur.fetchall()]
