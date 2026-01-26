#!/usr/bin/env python3
"""Price Watch データモデル.

型安全な dataclass を使用したデータモデルを定義します。
dict[str, Any] の代わりにこれらのクラスを使用することで、
型安全性とコードの可読性を向上させます。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CrawlStatus(Enum):
    """クロールステータス."""

    SUCCESS = 1
    FAILURE = 0


class StockStatus(Enum):
    """在庫ステータス."""

    IN_STOCK = 1
    OUT_OF_STOCK = 0
    UNKNOWN = -1

    @classmethod
    def from_int(cls, value: int | None) -> StockStatus:
        """整数値から StockStatus に変換.

        Args:
            value: 在庫状態値（0: 在庫なし, 1: 在庫あり, None: 不明）

        Returns:
            対応する StockStatus
        """
        if value is None:
            return cls.UNKNOWN
        if value == 1:
            return cls.IN_STOCK
        return cls.OUT_OF_STOCK

    def to_int(self) -> int | None:
        """整数値に変換.

        Returns:
            1 (在庫あり), 0 (在庫なし), None (不明)
        """
        if self == StockStatus.IN_STOCK:
            return 1
        if self == StockStatus.OUT_OF_STOCK:
            return 0
        return None


@dataclass(frozen=True)
class PriceResult:
    """価格チェック結果.

    スクレイピングや PA-API から取得した価格情報を保持します。
    """

    price: int | None
    stock: StockStatus
    crawl_status: CrawlStatus
    thumb_url: str | None = None


@dataclass
class CheckedItem:
    """チェック済みアイテム.

    価格チェック後のアイテム情報を保持します。
    スクレイピング、PA-API、メルカリ検索で共通のデータ構造として使用します。
    """

    name: str
    store: str
    url: str | None
    price: int | None = None
    stock: StockStatus = StockStatus.UNKNOWN
    crawl_status: CrawlStatus = CrawlStatus.FAILURE
    thumb_url: str | None = None
    price_unit: str = "円"
    point_rate: float = 0.0
    color: str | None = None
    # メルカリ検索用
    search_keyword: str | None = None
    search_cond: str | None = None
    # ASIN（Amazon 用）
    asin: str | None = None
    # 過去の価格（イベント判定用）
    old_price: int | None = None

    def is_success(self) -> bool:
        """クロール成功かどうかを返す."""
        return self.crawl_status == CrawlStatus.SUCCESS


@dataclass(frozen=True)
class PriceRecord:
    """価格履歴レコード.

    データベースから取得した価格履歴を表現します。
    """

    price: int | None
    stock: int | None
    crawl_status: int
    time: str


@dataclass(frozen=True)
class ItemRecord:
    """アイテムレコード.

    データベースのアイテム情報を表現します。
    """

    id: int
    item_key: str
    url: str | None
    name: str
    store: str
    thumb_url: str | None = None
    search_keyword: str | None = None
    search_cond: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class ItemStats:
    """アイテム統計情報."""

    lowest_price: int | None
    highest_price: int | None
    data_count: int


@dataclass(frozen=True)
class EventRecord:
    """イベントレコード.

    データベースのイベント情報を表現します。
    """

    id: int
    item_id: int
    event_type: str
    price: int | None
    old_price: int | None
    threshold_days: int | None
    created_at: str
    notified: bool
    # アイテム情報（JOIN 結果）
    item_name: str | None = None
    store: str | None = None
    url: str | None = None
    thumb_url: str | None = None


@dataclass
class ProcessResult:
    """処理結果.

    アイテムリストの処理結果を集約します。
    """

    total_items: int = 0
    success_count: int = 0
    failed_count: int = 0

    def record_success(self) -> None:
        """成功を記録."""
        self.total_items += 1
        self.success_count += 1

    def record_failure(self) -> None:
        """失敗を記録."""
        self.total_items += 1
        self.failed_count += 1


@dataclass
class SessionStats:
    """セッション統計.

    巡回セッションの統計情報を保持します。
    """

    session_id: int | None = None
    total_items: int = 0
    success_items: int = 0
    failed_items: int = 0

    def record_success(self) -> None:
        """成功を記録."""
        self.total_items += 1
        self.success_items += 1

    def record_failure(self) -> None:
        """失敗を記録."""
        self.total_items += 1
        self.failed_items += 1


@dataclass
class StoreStats:
    """ストア別統計.

    ストアごとの巡回統計情報を保持します。
    """

    store_name: str
    stats_id: int | None = None
    item_count: int = 0
    success_count: int = 0
    failed_count: int = 0


@dataclass(frozen=True)
class MercariSearchResult:
    """メルカリ検索結果."""

    name: str
    price: int
    url: str
    thumb_url: str | None = None
    status: str | None = None  # 商品の状態（新品・未使用など）


@dataclass(frozen=True)
class MercariSearchCondition:
    """メルカリ検索条件."""

    keyword: str
    exclude_keyword: str | None = None
    price_min: int | None = None
    price_max: int | None = None
    conditions: list[str] = field(default_factory=list)  # NEW, LIKE_NEW など

    def to_json(self) -> str:
        """JSON 文字列に変換."""
        import json

        return json.dumps(
            {
                "keyword": self.keyword,
                "exclude_keyword": self.exclude_keyword,
                "price_min": self.price_min,
                "price_max": self.price_max,
                "conditions": self.conditions,
            },
            ensure_ascii=False,
        )
