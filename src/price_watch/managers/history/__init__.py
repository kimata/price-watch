#!/usr/bin/env python3
"""履歴管理モジュール.

価格履歴の管理機能を提供します。
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from price_watch.managers.history.connection import HistoryDBConnection
from price_watch.managers.history.event_repository import EventRepository
from price_watch.managers.history.item_repository import ItemRepository
from price_watch.managers.history.price_repository import PriceRepository
from price_watch.managers.history.utils import generate_item_key, url_hash

if TYPE_CHECKING:
    from price_watch.models import (
        CheckedItem,
        EventRecord,
        ItemRecord,
        ItemStats,
        LatestPriceRecord,
        PriceHistoryRecord,
        PriceRecord,
    )

__all__ = [
    "EventRepository",
    "HistoryDBConnection",
    "HistoryManager",
    "ItemRepository",
    "PriceRepository",
    "generate_item_key",
    "url_hash",
]


@dataclass
class HistoryManager:
    """履歴管理マネージャー.

    価格履歴、アイテム、イベントの管理機能を統合して提供します。
    """

    db: HistoryDBConnection
    items: ItemRepository = field(init=False)
    prices: PriceRepository = field(init=False)
    events: EventRepository = field(init=False)

    def __post_init__(self) -> None:
        """Repository インスタンスを初期化."""
        self.items = ItemRepository(db=self.db)
        self.prices = PriceRepository(db=self.db, item_repo=self.items)
        self.events = EventRepository(db=self.db)

    @classmethod
    def create(cls, data_path: pathlib.Path) -> HistoryManager:
        """データパスから HistoryManager を作成.

        Args:
            data_path: データディレクトリパス

        Returns:
            HistoryManager インスタンス
        """
        db = HistoryDBConnection.create(data_path)
        return cls(db=db)

    def initialize(self) -> None:
        """データベースを初期化.

        テーブルとインデックスを作成します。
        """
        self.db.initialize()

    # --- 後方互換性のための委譲メソッド ---

    def insert(self, item: dict[str, Any], *, crawl_status: int = 1) -> int:
        """価格履歴を挿入または更新.

        Args:
            item: アイテム情報
            crawl_status: クロール状態（0: 失敗, 1: 成功）

        Returns:
            アイテム ID
        """
        return self.prices.insert(item, crawl_status=crawl_status)

    def get_last(self, url: str | None = None, *, item_key: str | None = None) -> PriceHistoryRecord | None:
        """最新の価格履歴を取得.

        Args:
            url: URL
            item_key: アイテムキー

        Returns:
            最新の価格履歴、または None
        """
        return self.prices.get_last(url, item_key=item_key)

    def get_lowest(self, url: str | None = None, *, item_key: str | None = None) -> PriceHistoryRecord | None:
        """最安値の価格履歴を取得.

        Args:
            url: URL
            item_key: アイテムキー

        Returns:
            最安値の価格履歴、または None
        """
        return self.prices.get_lowest(url, item_key=item_key)

    def get_history(
        self, item_key: str, days: int | None = None
    ) -> tuple[ItemRecord | None, list[PriceRecord]]:
        """アイテムの価格履歴を取得.

        Args:
            item_key: アイテムキー
            days: 期間（日数）

        Returns:
            (アイテム情報, 価格履歴リスト) のタプル
        """
        return self.prices.get_history(item_key, days)

    def get_item_id(self, url: str | None = None, *, item_key: str | None = None) -> int | None:
        """アイテム ID を取得.

        Args:
            url: URL
            item_key: アイテムキー

        Returns:
            アイテム ID、または None
        """
        return self.items.get_id(url, item_key=item_key)

    def get_item_by_id(self, item_id: int) -> ItemRecord | None:
        """アイテム ID からアイテム情報を取得.

        Args:
            item_id: アイテム ID

        Returns:
            アイテム情報、または None
        """
        return self.items.get_by_id(item_id)

    def get_all_items(self) -> list[ItemRecord]:
        """全アイテムを取得.

        Returns:
            アイテムリスト
        """
        return self.items.get_all()

    def insert_event(
        self,
        item_id: int,
        event_type: str,
        *,
        price: int | None = None,
        old_price: int | None = None,
        threshold_days: int | None = None,
        url: str | None = None,
        notified: bool = False,
    ) -> int:
        """イベントを記録.

        Args:
            item_id: アイテム ID
            event_type: イベントタイプ
            price: 現在価格
            old_price: 以前の価格
            threshold_days: 判定に使用した期間
            url: イベント発生時点の URL（スナップショット）
            notified: 通知済みフラグ

        Returns:
            イベント ID
        """
        return self.events.insert(
            item_id,
            event_type,
            price=price,
            old_price=old_price,
            threshold_days=threshold_days,
            url=url,
            notified=notified,
        )

    def get_last_event(self, item_id: int, event_type: str) -> EventRecord | None:
        """指定タイプの最新イベントを取得.

        Args:
            item_id: アイテム ID
            event_type: イベントタイプ

        Returns:
            イベント情報、または None
        """
        return self.events.get_last(item_id, event_type)

    def has_event_in_hours(self, item_id: int, event_type: str, hours: int) -> bool:
        """指定時間内に同じイベントが発生しているか確認.

        Args:
            item_id: アイテム ID
            event_type: イベントタイプ
            hours: 確認する時間数

        Returns:
            イベントがあれば True
        """
        return self.events.has_event_in_hours(item_id, event_type, hours)

    def get_recent_events(self, limit: int = 10) -> list[EventRecord]:
        """最新のイベントを取得.

        Args:
            limit: 取得件数上限

        Returns:
            イベントのリスト
        """
        return self.events.get_recent(limit)

    def mark_event_notified(self, event_id: int) -> None:
        """イベントを通知済みにする.

        Args:
            event_id: イベント ID
        """
        self.events.mark_notified(event_id)

    def get_item_events(self, item_key: str, limit: int = 50) -> list[EventRecord]:
        """指定アイテムのイベント履歴を取得.

        Args:
            item_key: アイテムキー
            limit: 取得件数上限

        Returns:
            イベントのリスト
        """
        return self.events.get_by_item(item_key, limit)

    def get_stats(self, item_id: int, days: int | None = None) -> ItemStats:
        """アイテムの統計情報を取得.

        Args:
            item_id: アイテム ID
            days: 期間（日数）

        Returns:
            統計情報
        """
        return self.prices.get_stats(item_id, days)

    def get_latest(self, item_id: int) -> LatestPriceRecord | None:
        """アイテムの最新価格を取得.

        Args:
            item_id: アイテム ID

        Returns:
            最新価格情報、または None
        """
        return self.prices.get_latest(item_id)

    def get_lowest_in_period(self, item_id: int, days: int | None = None) -> int | None:
        """指定期間内の最安値を取得.

        Args:
            item_id: アイテム ID
            days: 期間（日数）

        Returns:
            最安値
        """
        return self.prices.get_lowest_in_period(item_id, days)

    def has_successful_crawl_in_hours(self, item_id: int, hours: int) -> bool:
        """指定時間内に成功したクロールがあるか確認.

        Args:
            item_id: アイテム ID
            hours: 確認する時間数

        Returns:
            成功したクロールがあれば True
        """
        return self.prices.has_successful_crawl_in_hours(item_id, hours)

    def get_out_of_stock_duration_hours(self, item_id: int) -> float | None:
        """在庫なし状態の継続時間を取得.

        Args:
            item_id: アイテム ID

        Returns:
            継続時間（時間）、または None
        """
        return self.prices.get_out_of_stock_duration_hours(item_id)

    def get_last_successful_crawl(self, item_id: int) -> LatestPriceRecord | None:
        """最後に成功したクロールを取得.

        Args:
            item_id: アイテム ID

        Returns:
            クロール情報、または None
        """
        return self.prices.get_last_successful_crawl(item_id)

    def get_no_data_duration_hours(self, item_id: int) -> float | None:
        """データ取得失敗の継続時間を取得.

        Args:
            item_id: アイテム ID

        Returns:
            継続時間（時間）、または None
        """
        return self.prices.get_no_data_duration_hours(item_id)

    def upsert_item(self, item: CheckedItem) -> int:
        """アイテム情報のみを upsert（価格履歴は挿入しない）.

        Args:
            item: チェック済みアイテム

        Returns:
            アイテム ID
        """
        item_dict = {
            "name": item.name,
            "store": item.store,
            "url": item.url,
            "thumb_url": item.thumb_url,
            "search_keyword": item.search_keyword,
            "search_cond": item.search_cond,
        }
        return self.prices.upsert_item(item_dict)

    def insert_price_history(self, item_id: int, item: CheckedItem) -> None:
        """価格履歴のみを挿入.

        Args:
            item_id: アイテム ID
            item: チェック済みアイテム
        """
        crawl_status = 1 if item.is_success() else 0
        self.prices.insert_price_history(
            item_id,
            item.price,
            item.stock.to_int(),
            crawl_status,
        )

    def insert_checked_item(self, item: CheckedItem) -> int:
        """CheckedItem から価格履歴を挿入.

        Args:
            item: チェック済みアイテム

        Returns:
            アイテム ID
        """
        item_id = self.upsert_item(item)
        self.insert_price_history(item_id, item)
        return item_id

    @staticmethod
    def generate_item_key(
        url: str | None = None,
        *,
        search_keyword: str | None = None,
        search_cond: str | None = None,
        store_name: str | None = None,
    ) -> str:
        """アイテムキーを生成.

        Args:
            url: URL（通常ストア用）
            search_keyword: 検索キーワード（検索系ストア用）
            search_cond: 検索条件（未使用）
            store_name: ストア名（検索系ストア用、ハッシュに含める）

        Returns:
            12文字のハッシュ
        """
        return generate_item_key(
            url, search_keyword=search_keyword, search_cond=search_cond, store_name=store_name
        )
