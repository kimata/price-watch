#!/usr/bin/env python3
# ruff: noqa: S101
"""
history.py のユニットテスト

SQLite ベースの価格履歴管理を検証します。
"""

from __future__ import annotations

import pathlib
import sqlite3
from collections.abc import Generator
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import price_watch.history


@pytest.fixture
def history_db(tmp_path: pathlib.Path) -> Generator[pathlib.Path, None, None]:
    """history テスト用の DB を初期化するフィクスチャ."""
    # 現在のグローバル状態を保存
    old_data_path = price_watch.history._data_path

    # 新しいパスで初期化
    price_watch.history.init(tmp_path)

    yield tmp_path

    # グローバル状態を復元
    price_watch.history._data_path = old_data_path


class TestDictFactory:
    """_dict_factory のテスト"""

    def test_converts_row_to_dict(self) -> None:
        """行を辞書に変換"""
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",), ("price",)]
        row = (1, "Item1", 1000)

        result = price_watch.history._dict_factory(mock_cursor, row)

        assert result == {"id": 1, "name": "Item1", "price": 1000}

    def test_handles_empty_row(self) -> None:
        """空の行を処理"""
        mock_cursor = MagicMock()
        mock_cursor.description = []
        row: tuple[Any, ...] = ()

        result = price_watch.history._dict_factory(mock_cursor, row)

        assert result == {}


class TestUrlHash:
    """_url_hash と url_hash のテスト"""

    def test_generates_hash(self) -> None:
        """URL からハッシュを生成"""
        result = price_watch.history._url_hash("http://example.com")

        assert len(result) == 12
        assert result.isalnum()

    def test_same_url_same_hash(self) -> None:
        """同じ URL は同じハッシュ"""
        url = "http://example.com/product/123"
        result1 = price_watch.history._url_hash(url)
        result2 = price_watch.history._url_hash(url)

        assert result1 == result2

    def test_different_url_different_hash(self) -> None:
        """異なる URL は異なるハッシュ"""
        result1 = price_watch.history._url_hash("http://example.com/1")
        result2 = price_watch.history._url_hash("http://example.com/2")

        assert result1 != result2

    def test_public_api_same_as_private(self) -> None:
        """公開 API は内部と同じ結果"""
        url = "http://example.com"
        assert price_watch.history.url_hash(url) == price_watch.history._url_hash(url)


class TestGenerateItemKey:
    """generate_item_key のテスト"""

    def test_generates_from_url(self) -> None:
        """URL からキーを生成"""
        result = price_watch.history.generate_item_key("http://example.com")

        assert len(result) == 12

    def test_generates_from_search_keyword(self) -> None:
        """検索キーワードからキーを生成"""
        result = price_watch.history.generate_item_key(search_keyword="test keyword")

        assert len(result) == 12

    def test_keyword_priority_over_url(self) -> None:
        """キーワードは URL より優先"""
        result_url = price_watch.history.generate_item_key("http://example.com")
        result_keyword = price_watch.history.generate_item_key("http://example.com", search_keyword="test")

        assert result_url != result_keyword

    def test_search_cond_ignored(self) -> None:
        """search_cond は無視される"""
        result1 = price_watch.history.generate_item_key(search_keyword="test", search_cond="cond1")
        result2 = price_watch.history.generate_item_key(search_keyword="test", search_cond="cond2")

        assert result1 == result2

    def test_raises_without_url_or_keyword(self) -> None:
        """URL もキーワードもない場合は例外"""
        with pytest.raises(ValueError, match="Either url or search_keyword"):
            price_watch.history.generate_item_key()


class TestInit:
    """init 関数のテスト"""

    def test_creates_tables(self, tmp_path: pathlib.Path) -> None:
        """テーブルを作成"""
        # 直接 init を呼んで DB を作成
        price_watch.history.init(tmp_path)
        db_path = tmp_path / "price_history.db"
        assert db_path.exists()

        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}

        assert "items" in tables
        assert "price_history" in tables
        assert "events" in tables

    def test_creates_indexes(self, tmp_path: pathlib.Path) -> None:
        """インデックスを作成"""
        price_watch.history.init(tmp_path)
        db_path = tmp_path / "price_history.db"
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = {row[0] for row in cur.fetchall()}

        assert "idx_items_item_key" in indexes
        assert "idx_price_history_item_id" in indexes
        assert "idx_price_history_time" in indexes
        assert "idx_events_item_id" in indexes

    def test_creates_directory_if_not_exists(self, tmp_path: pathlib.Path) -> None:
        """ディレクトリがなければ作成"""
        data_path = tmp_path / "nested" / "dir"
        assert not data_path.exists()

        price_watch.history.init(data_path)

        assert data_path.exists()

    def test_idempotent(self, tmp_path: pathlib.Path) -> None:
        """複数回呼んでも安全"""
        price_watch.history.init(tmp_path)
        price_watch.history.init(tmp_path)

        # エラーが発生しなければ OK


class TestInsert:
    """insert 関数のテスト"""

    def test_inserts_new_item(self, history_db: pathlib.Path) -> None:
        """新規アイテムを挿入"""
        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": "http://example.com/item1",
            "price": 1000,
            "stock": 1,
        }

        item_id = price_watch.history.insert(item)

        assert item_id > 0

    def test_inserts_with_thumb_url(self, history_db: pathlib.Path) -> None:
        """サムネイル URL 付きで挿入"""
        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": "http://example.com/item2",
            "price": 1000,
            "stock": 1,
            "thumb_url": "http://example.com/thumb.jpg",
        }

        item_id = price_watch.history.insert(item)

        result = price_watch.history.get_item_by_id(item_id)
        assert result is not None
        assert result["thumb_url"] == "http://example.com/thumb.jpg"

    def test_inserts_mercari_item(self, history_db: pathlib.Path) -> None:
        """メルカリアイテムを挿入"""
        item = {
            "name": "Mercari Item",
            "store": "メルカリ",
            "url": "http://mercari.com/item123",
            "search_keyword": "test keyword",
            "search_cond": '{"price_min": 100}',
            "price": 500,
            "stock": 1,
        }

        item_id = price_watch.history.insert(item)

        result = price_watch.history.get_item_by_id(item_id)
        assert result is not None
        assert result["search_keyword"] == "test keyword"

    def test_inserts_with_crawl_status_failure(self, history_db: pathlib.Path) -> None:
        """クロール失敗時の挿入"""
        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": "http://example.com/item3",
        }

        item_id = price_watch.history.insert(item, crawl_status=0)

        result = price_watch.history.get_latest_price(item_id)
        assert result is not None
        assert result["price"] is None
        assert result["stock"] is None

    def test_updates_existing_item_name(self, history_db: pathlib.Path) -> None:
        """既存アイテムの名前を更新"""
        url = "http://example.com/item4"

        item1 = {
            "name": "Original Name",
            "store": "Test Store",
            "url": url,
            "price": 1000,
            "stock": 1,
        }
        item_id = price_watch.history.insert(item1)

        with patch("my_lib.time.now") as mock_now:
            mock_now.return_value = datetime.now() + timedelta(hours=2)
            item2 = {
                "name": "Updated Name",
                "store": "Test Store",
                "url": url,
                "price": 1100,
                "stock": 1,
            }
            item_id2 = price_watch.history.insert(item2)

        assert item_id == item_id2

        result = price_watch.history.get_item_by_id(item_id)
        assert result is not None
        assert result["name"] == "Updated Name"


class TestLast:
    """last 関数のテスト"""

    def test_returns_latest_price(self, history_db: pathlib.Path) -> None:
        """最新の価格履歴を取得"""
        url = "http://example.com/last1"

        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": url,
            "price": 1000,
            "stock": 1,
        }
        price_watch.history.insert(item)

        result = price_watch.history.last(url)

        assert result is not None
        assert result["price"] == 1000
        assert result["name"] == "Test Item"

    def test_returns_none_for_unknown_url(self, history_db: pathlib.Path) -> None:
        """不明な URL は None を返す"""
        result = price_watch.history.last("http://unknown.com")

        assert result is None

    def test_uses_item_key_if_provided(self, history_db: pathlib.Path) -> None:
        """item_key が指定されていればそれを使う"""
        url = "http://example.com/last2"
        item_key = price_watch.history.generate_item_key(url)

        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": url,
            "price": 1000,
            "stock": 1,
        }
        price_watch.history.insert(item)

        result = price_watch.history.last(item_key=item_key)

        assert result is not None
        assert result["price"] == 1000

    def test_returns_none_without_url_or_key(self, history_db: pathlib.Path) -> None:
        """URL も key もない場合は None"""
        result = price_watch.history.last()

        assert result is None


class TestLowest:
    """lowest 関数のテスト"""

    def test_returns_lowest_price(self, history_db: pathlib.Path) -> None:
        """最安値を取得"""
        url = "http://example.com/lowest1"

        base_time = datetime(2024, 1, 1, 10, 0, 0)
        for i, price in enumerate([1500, 1000, 1200]):
            with patch("my_lib.time.now") as mock_now:
                mock_now.return_value = base_time + timedelta(hours=i)
                item = {
                    "name": "Test Item",
                    "store": "Test Store",
                    "url": url,
                    "price": price,
                    "stock": 1,
                }
                price_watch.history.insert(item)

        result = price_watch.history.lowest(url)

        assert result is not None
        assert result["price"] == 1000

    def test_excludes_null_price(self, history_db: pathlib.Path) -> None:
        """価格が NULL のレコードは除外"""
        url = "http://example.com/lowest2"

        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": url,
            "price": 1000,
            "stock": 1,
        }
        price_watch.history.insert(item)

        with patch("my_lib.time.now") as mock_now:
            mock_now.return_value = datetime.now() + timedelta(hours=2)
            price_watch.history.insert(item, crawl_status=0)

        result = price_watch.history.lowest(url)

        assert result is not None
        assert result["price"] == 1000

    def test_returns_none_for_unknown_url(self, history_db: pathlib.Path) -> None:
        """不明な URL は None を返す"""
        result = price_watch.history.lowest("http://unknown.com")

        assert result is None


class TestGetAllItems:
    """get_all_items 関数のテスト"""

    def test_returns_all_items(self, history_db: pathlib.Path) -> None:
        """全アイテムを取得"""
        for i in range(3):
            item = {
                "name": f"Item {i}",
                "store": "Store",
                "url": f"http://example.com/all{i}",
                "price": 1000 + i * 100,
                "stock": 1,
            }
            price_watch.history.insert(item)

        result = price_watch.history.get_all_items()

        assert len(result) == 3

    def test_returns_empty_for_empty_db(self, history_db: pathlib.Path) -> None:
        """空の DB では空リスト"""
        result = price_watch.history.get_all_items()

        assert result == []


class TestGetItemHistory:
    """get_item_history 関数のテスト"""

    def test_returns_item_and_history(self, history_db: pathlib.Path) -> None:
        """アイテム情報と履歴を取得"""
        url = "http://example.com/history1"
        item_key = price_watch.history.generate_item_key(url)

        base_time = datetime(2024, 1, 1, 10, 0, 0)
        for i in range(3):
            with patch("my_lib.time.now") as mock_now:
                mock_now.return_value = base_time + timedelta(hours=i)
                item = {
                    "name": "Test Item",
                    "store": "Test Store",
                    "url": url,
                    "price": 1000 + i * 100,
                    "stock": 1,
                }
                price_watch.history.insert(item)

        item_info, history = price_watch.history.get_item_history(item_key)

        assert item_info is not None
        assert item_info["name"] == "Test Item"
        assert len(history) == 3

    def test_returns_history_with_days_filter(self, history_db: pathlib.Path) -> None:
        """日数フィルター付きで履歴を取得"""
        url = "http://example.com/history2"
        item_key = price_watch.history.generate_item_key(url)

        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": url,
            "price": 1000,
            "stock": 1,
        }
        price_watch.history.insert(item)

        item_info, history = price_watch.history.get_item_history(item_key, days=7)

        assert item_info is not None
        assert len(history) >= 1

    def test_returns_none_for_unknown_key(self, history_db: pathlib.Path) -> None:
        """不明なキーは (None, []) を返す"""
        item_info, history = price_watch.history.get_item_history("unknown_key")

        assert item_info is None
        assert history == []


class TestGetItemStats:
    """get_item_stats 関数のテスト"""

    def test_returns_statistics(self, history_db: pathlib.Path) -> None:
        """統計情報を取得"""
        url = "http://example.com/stats1"

        base_time = datetime(2024, 1, 1, 10, 0, 0)
        for i, price in enumerate([1500, 1000, 1200]):
            with patch("my_lib.time.now") as mock_now:
                mock_now.return_value = base_time + timedelta(hours=i)
                item = {
                    "name": "Test Item",
                    "store": "Test Store",
                    "url": url,
                    "price": price,
                    "stock": 1,
                }
                price_watch.history.insert(item)

        item_id = price_watch.history.get_item_id(url)
        assert item_id is not None

        stats = price_watch.history.get_item_stats(item_id)

        assert stats["lowest_price"] == 1000
        assert stats["highest_price"] == 1500
        assert stats["data_count"] == 3

    def test_returns_default_for_no_data(self, history_db: pathlib.Path) -> None:
        """データがない場合はデフォルト値"""
        stats = price_watch.history.get_item_stats(999)

        assert stats["lowest_price"] is None
        assert stats["highest_price"] is None
        assert stats["data_count"] == 0


class TestGetLatestPrice:
    """get_latest_price 関数のテスト"""

    def test_returns_latest(self, history_db: pathlib.Path) -> None:
        """最新価格を取得"""
        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": "http://example.com/latest1",
            "price": 1000,
            "stock": 1,
        }
        item_id = price_watch.history.insert(item)

        result = price_watch.history.get_latest_price(item_id)

        assert result is not None
        assert result["price"] == 1000
        assert result["stock"] == 1

    def test_returns_none_for_unknown(self, history_db: pathlib.Path) -> None:
        """不明な ID は None"""
        result = price_watch.history.get_latest_price(999)

        assert result is None


class TestGetItemId:
    """get_item_id 関数のテスト"""

    def test_returns_item_id(self, history_db: pathlib.Path) -> None:
        """アイテム ID を取得"""
        url = "http://example.com/itemid1"

        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": url,
            "price": 1000,
            "stock": 1,
        }
        expected_id = price_watch.history.insert(item)

        result = price_watch.history.get_item_id(url)

        assert result == expected_id

    def test_returns_none_for_unknown(self, history_db: pathlib.Path) -> None:
        """不明な URL は None"""
        result = price_watch.history.get_item_id("http://unknown.com")

        assert result is None

    def test_uses_item_key_if_provided(self, history_db: pathlib.Path) -> None:
        """item_key が指定されていればそれを使う"""
        url = "http://example.com/itemid2"
        item_key = price_watch.history.generate_item_key(url)

        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": url,
            "price": 1000,
            "stock": 1,
        }
        expected_id = price_watch.history.insert(item)

        result = price_watch.history.get_item_id(item_key=item_key)

        assert result == expected_id


class TestGetItemById:
    """get_item_by_id 関数のテスト"""

    def test_returns_item(self, history_db: pathlib.Path) -> None:
        """アイテム情報を取得"""
        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": "http://example.com/byid1",
            "price": 1000,
            "stock": 1,
        }
        item_id = price_watch.history.insert(item)

        result = price_watch.history.get_item_by_id(item_id)

        assert result is not None
        assert result["name"] == "Test Item"
        assert result["store"] == "Test Store"

    def test_returns_none_for_unknown(self, history_db: pathlib.Path) -> None:
        """不明な ID は None"""
        result = price_watch.history.get_item_by_id(999)

        assert result is None


class TestGetLowestPriceInPeriod:
    """get_lowest_price_in_period 関数のテスト"""

    def test_returns_lowest_in_period(self, history_db: pathlib.Path) -> None:
        """指定期間内の最安値を取得"""
        url = "http://example.com/lowestperiod1"

        base_time = datetime(2024, 1, 1, 10, 0, 0)
        for i, price in enumerate([1500, 1000, 1200]):
            with patch("my_lib.time.now") as mock_now:
                mock_now.return_value = base_time + timedelta(hours=i)
                item = {
                    "name": "Test Item",
                    "store": "Test Store",
                    "url": url,
                    "price": price,
                    "stock": 1,
                }
                price_watch.history.insert(item)

        item_id = price_watch.history.get_item_id(url)
        assert item_id is not None

        result = price_watch.history.get_lowest_price_in_period(item_id)

        assert result == 1000

    def test_returns_none_for_no_data(self, history_db: pathlib.Path) -> None:
        """データがない場合は None"""
        result = price_watch.history.get_lowest_price_in_period(999)

        assert result is None


class TestHasSuccessfulCrawlInHours:
    """has_successful_crawl_in_hours 関数のテスト"""

    def test_returns_true_if_exists(self, history_db: pathlib.Path) -> None:
        """成功クロールがあれば True"""
        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": "http://example.com/crawl1",
            "price": 1000,
            "stock": 1,
        }
        item_id = price_watch.history.insert(item)

        result = price_watch.history.has_successful_crawl_in_hours(item_id, 1)

        assert result is True

    def test_returns_false_if_not_exists(self, history_db: pathlib.Path) -> None:
        """成功クロールがなければ False"""
        result = price_watch.history.has_successful_crawl_in_hours(999, 1)

        assert result is False


class TestGetOutOfStockDurationHours:
    """get_out_of_stock_duration_hours 関数のテスト"""

    def test_returns_duration(self, history_db: pathlib.Path) -> None:
        """在庫なし継続時間を取得"""
        url = "http://example.com/outofstock1"

        with patch("my_lib.time.now") as mock_now:
            mock_now.return_value = datetime.now() - timedelta(hours=5)
            item = {
                "name": "Test Item",
                "store": "Test Store",
                "url": url,
                "price": None,
                "stock": 0,
            }
            item_id = price_watch.history.insert(item)

        result = price_watch.history.get_out_of_stock_duration_hours(item_id)

        assert result is not None
        assert result >= 4.9

    def test_returns_none_if_in_stock(self, history_db: pathlib.Path) -> None:
        """在庫ありの場合は None"""
        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": "http://example.com/outofstock2",
            "price": 1000,
            "stock": 1,
        }
        item_id = price_watch.history.insert(item)

        result = price_watch.history.get_out_of_stock_duration_hours(item_id)

        assert result is None


class TestGetLastSuccessfulCrawl:
    """get_last_successful_crawl 関数のテスト"""

    def test_returns_last_success(self, history_db: pathlib.Path) -> None:
        """最後の成功クロールを取得"""
        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": "http://example.com/lastcrawl1",
            "price": 1000,
            "stock": 1,
        }
        item_id = price_watch.history.insert(item)

        result = price_watch.history.get_last_successful_crawl(item_id)

        assert result is not None
        assert result["price"] == 1000
        assert result["crawl_status"] == 1

    def test_returns_none_for_no_success(self, history_db: pathlib.Path) -> None:
        """成功がない場合は None"""
        result = price_watch.history.get_last_successful_crawl(999)

        assert result is None


class TestGetNoDataDurationHours:
    """get_no_data_duration_hours 関数のテスト"""

    def test_returns_duration_for_crawl_failure(self, history_db: pathlib.Path) -> None:
        """クロール失敗の継続時間を取得"""
        url = "http://example.com/nodata1"

        with patch("my_lib.time.now") as mock_now:
            mock_now.return_value = datetime.now() - timedelta(hours=3)
            item = {
                "name": "Test Item",
                "store": "Test Store",
                "url": url,
            }
            item_id = price_watch.history.insert(item, crawl_status=0)

        result = price_watch.history.get_no_data_duration_hours(item_id)

        assert result is not None
        assert result >= 2.9

    def test_returns_none_if_data_exists(self, history_db: pathlib.Path) -> None:
        """データがある場合は None"""
        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": "http://example.com/nodata2",
            "price": 1000,
            "stock": 1,
        }
        item_id = price_watch.history.insert(item)

        result = price_watch.history.get_no_data_duration_hours(item_id)

        assert result is None


class TestInsertEvent:
    """insert_event 関数のテスト"""

    def test_inserts_event(self, history_db: pathlib.Path) -> None:
        """イベントを挿入"""
        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": "http://example.com/event1",
            "price": 1000,
            "stock": 1,
        }
        item_id = price_watch.history.insert(item)

        event_id = price_watch.history.insert_event(
            item_id,
            "PRICE_DROP",
            price=900,
            old_price=1000,
            threshold_days=30,
        )

        assert event_id > 0

    def test_inserts_with_notified_flag(self, history_db: pathlib.Path) -> None:
        """通知済みフラグ付きで挿入"""
        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": "http://example.com/event2",
            "price": 1000,
            "stock": 1,
        }
        item_id = price_watch.history.insert(item)

        price_watch.history.insert_event(item_id, "STOCK_RESTORED", notified=True)

        event = price_watch.history.get_last_event(item_id, "STOCK_RESTORED")
        assert event is not None
        assert event["notified"] == 1


class TestGetLastEvent:
    """get_last_event 関数のテスト"""

    def test_returns_last_event(self, history_db: pathlib.Path) -> None:
        """最新イベントを取得"""
        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": "http://example.com/lastevent1",
            "price": 1000,
            "stock": 1,
        }
        item_id = price_watch.history.insert(item)

        price_watch.history.insert_event(item_id, "PRICE_DROP", price=900)

        with patch("my_lib.time.now") as mock_now:
            mock_now.return_value = datetime.now() + timedelta(seconds=1)
            price_watch.history.insert_event(item_id, "PRICE_DROP", price=800)

        result = price_watch.history.get_last_event(item_id, "PRICE_DROP")

        assert result is not None
        assert result["price"] == 800

    def test_returns_none_for_no_event(self, history_db: pathlib.Path) -> None:
        """イベントがない場合は None"""
        result = price_watch.history.get_last_event(999, "PRICE_DROP")

        assert result is None


class TestHasEventInHours:
    """has_event_in_hours 関数のテスト"""

    def test_returns_true_if_exists(self, history_db: pathlib.Path) -> None:
        """イベントがあれば True"""
        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": "http://example.com/hasevent1",
            "price": 1000,
            "stock": 1,
        }
        item_id = price_watch.history.insert(item)
        price_watch.history.insert_event(item_id, "PRICE_DROP")

        result = price_watch.history.has_event_in_hours(item_id, "PRICE_DROP", 1)

        assert result is True

    def test_returns_false_if_not_exists(self, history_db: pathlib.Path) -> None:
        """イベントがなければ False"""
        result = price_watch.history.has_event_in_hours(999, "PRICE_DROP", 1)

        assert result is False


class TestGetRecentEvents:
    """get_recent_events 関数のテスト"""

    def test_returns_recent_events(self, history_db: pathlib.Path) -> None:
        """最新イベントを取得"""
        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": "http://example.com/recent1",
            "price": 1000,
            "stock": 1,
        }
        item_id = price_watch.history.insert(item)

        for i in range(5):
            price_watch.history.insert_event(item_id, "PRICE_DROP", price=1000 - i * 100)

        result = price_watch.history.get_recent_events(limit=3)

        assert len(result) == 3

    def test_includes_item_info(self, history_db: pathlib.Path) -> None:
        """アイテム情報を含む"""
        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": "http://example.com/recent2",
            "price": 1000,
            "stock": 1,
        }
        item_id = price_watch.history.insert(item)
        price_watch.history.insert_event(item_id, "PRICE_DROP")

        result = price_watch.history.get_recent_events(limit=1)

        assert len(result) == 1
        assert result[0]["item_name"] == "Test Item"
        assert result[0]["store"] == "Test Store"


class TestMarkEventNotified:
    """mark_event_notified 関数のテスト"""

    def test_marks_as_notified(self, history_db: pathlib.Path) -> None:
        """通知済みにマーク"""
        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": "http://example.com/marknotify1",
            "price": 1000,
            "stock": 1,
        }
        item_id = price_watch.history.insert(item)
        event_id = price_watch.history.insert_event(item_id, "PRICE_DROP", notified=False)

        price_watch.history.mark_event_notified(event_id)

        event = price_watch.history.get_last_event(item_id, "PRICE_DROP")
        assert event is not None
        assert event["notified"] == 1


class TestGetItemEvents:
    """get_item_events 関数のテスト"""

    def test_returns_item_events(self, history_db: pathlib.Path) -> None:
        """アイテムのイベント履歴を取得"""
        url = "http://example.com/itemevents1"
        item_key = price_watch.history.generate_item_key(url)

        item = {
            "name": "Test Item",
            "store": "Test Store",
            "url": url,
            "price": 1000,
            "stock": 1,
        }
        item_id = price_watch.history.insert(item)

        for i in range(3):
            price_watch.history.insert_event(item_id, "PRICE_DROP", price=1000 - i * 100)

        result = price_watch.history.get_item_events(item_key)

        assert len(result) == 3

    def test_returns_empty_for_unknown_key(self, history_db: pathlib.Path) -> None:
        """不明なキーは空リスト"""
        result = price_watch.history.get_item_events("unknown_key")

        assert result == []


class TestMigrateFromOldSchema:
    """migrate_from_old_schema 関数のテスト"""

    def test_skips_if_no_old_table(self, history_db: pathlib.Path) -> None:
        """旧テーブルがない場合はスキップ"""
        price_watch.history.migrate_from_old_schema()

    def test_skips_if_already_migrated(self, history_db: pathlib.Path) -> None:
        """既にマイグレーション済みならスキップ"""
        price_watch.history.migrate_from_old_schema()


class TestMigrateToNullablePrice:
    """migrate_to_nullable_price 関数のテスト"""

    def test_skips_if_no_table(self, history_db: pathlib.Path) -> None:
        """テーブルがない場合はスキップ"""
        db_path = history_db / "price_history.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute("DROP TABLE IF EXISTS price_history")

        price_watch.history.migrate_to_nullable_price()

    def test_skips_if_already_nullable(self, history_db: pathlib.Path) -> None:
        """既に NULL 許可なら何もしない"""
        price_watch.history.migrate_to_nullable_price()


class TestMigrateAddCrawlStatus:
    """migrate_add_crawl_status 関数のテスト"""

    def test_skips_if_no_table(self, history_db: pathlib.Path) -> None:
        """テーブルがない場合はスキップ"""
        db_path = history_db / "price_history.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute("DROP TABLE IF EXISTS price_history")

        price_watch.history.migrate_add_crawl_status()

    def test_skips_if_column_exists(self, history_db: pathlib.Path) -> None:
        """既にカラムがあればスキップ"""
        price_watch.history.migrate_add_crawl_status()


class TestMigrateUrlHashToItemKey:
    """migrate_url_hash_to_item_key 関数のテスト"""

    def test_skips_if_no_table(self, tmp_path: pathlib.Path) -> None:
        """テーブルがない場合はスキップ"""
        price_watch.history.init(tmp_path)
        db_path = tmp_path / "price_history.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute("DROP TABLE IF EXISTS items")

        price_watch.history.migrate_url_hash_to_item_key()

    def test_skips_if_item_key_exists(self, tmp_path: pathlib.Path) -> None:
        """既に item_key があればスキップ"""
        price_watch.history.init(tmp_path)
        price_watch.history.migrate_url_hash_to_item_key()

    def test_migrates_from_url_hash(self, tmp_path: pathlib.Path) -> None:
        """url_hash から item_key にマイグレーション"""
        # 初期化してグローバル状態を設定
        price_watch.history.init(tmp_path)
        db_path = tmp_path / "price_history.db"

        # 旧スキーマでテーブルを再作成
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute("DROP TABLE IF EXISTS items")
            cur.execute(
                """
                CREATE TABLE items(
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    url_hash    TEXT NOT NULL UNIQUE,
                    url         TEXT NOT NULL,
                    name        TEXT NOT NULL,
                    store       TEXT NOT NULL,
                    thumb_url   TEXT,
                    created_at  TIMESTAMP,
                    updated_at  TIMESTAMP
                )
                """
            )
            cur.execute(
                """
                INSERT INTO items (url_hash, url, name, store)
                VALUES ('abc123', 'http://example.com', 'Test', 'Store')
                """
            )
            conn.commit()
        finally:
            conn.close()

        price_watch.history.migrate_url_hash_to_item_key()

        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(items)")
            columns = [row[1] for row in cur.fetchall()]
        finally:
            conn.close()

        assert "item_key" in columns
        assert "url_hash" not in columns
