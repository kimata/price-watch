#!/usr/bin/env python3
# ruff: noqa: S101
"""
target.py のユニットテスト
"""

from price_watch.target import (
    CheckMethod,
    ItemDefinition,
    ResolvedItem,
    StoreDefinition,
    TargetConfig,
)


class TestStoreDefinition:
    """StoreDefinition のテスト"""

    def test_parse_basic(self):
        """基本的なパース"""
        data = {"name": "test-store.com"}
        store = StoreDefinition.parse(data)

        assert store.name == "test-store.com"
        assert store.check_method == CheckMethod.SCRAPE
        assert store.point_rate == 0.0

    def test_parse_with_point_rate(self):
        """ポイント還元率付きパース"""
        data = {
            "name": "yodobashi.com",
            "point_rate": 10.0,
            "price_xpath": "//span[@class='price']",
        }
        store = StoreDefinition.parse(data)

        assert store.name == "yodobashi.com"
        assert store.point_rate == 10.0
        assert store.price_xpath == "//span[@class='price']"

    def test_parse_with_check_method(self):
        """チェックメソッド付きパース"""
        data = {
            "name": "amazon.co.jp",
            "check_method": "amazon-paapi",
        }
        store = StoreDefinition.parse(data)

        assert store.check_method == CheckMethod.AMAZON_PAAPI


class TestResolvedItem:
    """ResolvedItem のテスト"""

    def test_from_item_and_store_basic(self):
        """基本的なマージ"""
        item = ItemDefinition.parse(
            {
                "name": "Test Item",
                "store": "test-store.com",
                "url": "https://test-store.com/item/1",
            }
        )
        store = StoreDefinition.parse(
            {
                "name": "test-store.com",
                "price_xpath": "//span[@class='price']",
                "point_rate": 5.0,
            }
        )

        resolved = ResolvedItem.from_item_and_store(item, store)

        assert resolved.name == "Test Item"
        assert resolved.store == "test-store.com"
        assert resolved.url == "https://test-store.com/item/1"
        assert resolved.price_xpath == "//span[@class='price']"
        assert resolved.point_rate == 5.0

    def test_from_item_and_store_without_store(self):
        """ストア定義なしのマージ"""
        item = ItemDefinition.parse(
            {
                "name": "Test Item",
                "store": "unknown-store.com",
                "url": "https://unknown-store.com/item/1",
            }
        )

        resolved = ResolvedItem.from_item_and_store(item, None)

        assert resolved.name == "Test Item"
        assert resolved.point_rate == 0.0

    def test_to_dict_includes_point_rate(self):
        """to_dict が point_rate を含むこと"""
        item = ItemDefinition.parse(
            {
                "name": "Test Item",
                "store": "test-store.com",
                "url": "https://test-store.com/item/1",
            }
        )
        store = StoreDefinition.parse(
            {
                "name": "test-store.com",
                "point_rate": 10.0,
            }
        )

        resolved = ResolvedItem.from_item_and_store(item, store)
        result = resolved.to_dict()

        assert "point_rate" in result
        assert result["point_rate"] == 10.0

    def test_from_item_with_asin(self):
        """ASIN 付きアイテムのマージ"""
        item = ItemDefinition.parse(
            {
                "name": "Amazon Item",
                "store": "amazon.co.jp",
                "asin": "B0123456789",
            }
        )
        store = StoreDefinition.parse(
            {
                "name": "amazon.co.jp",
                "check_method": "amazon-paapi",
            }
        )

        resolved = ResolvedItem.from_item_and_store(item, store)

        assert resolved.asin == "B0123456789"
        assert resolved.url == "https://www.amazon.co.jp/dp/B0123456789"
        assert resolved.check_method == CheckMethod.AMAZON_PAAPI


class TestTargetConfig:
    """TargetConfig のテスト"""

    def test_parse_full(self):
        """完全なパース"""
        data = {
            "store_list": [
                {"name": "store1.com", "point_rate": 5.0},
                {"name": "store2.com", "point_rate": 10.0},
            ],
            "item_list": [
                {"name": "Item 1", "store": "store1.com", "url": "https://store1.com/1"},
                {"name": "Item 2", "store": "store2.com", "url": "https://store2.com/2"},
            ],
        }

        config = TargetConfig.parse(data)

        assert len(config.stores) == 2
        assert len(config.items) == 2
        assert config.stores[0].point_rate == 5.0
        assert config.stores[1].point_rate == 10.0

    def test_get_store(self):
        """ストア取得"""
        data = {
            "store_list": [
                {"name": "store1.com", "point_rate": 5.0},
                {"name": "store2.com", "point_rate": 10.0},
            ],
            "item_list": [],
        }

        config = TargetConfig.parse(data)

        store = config.get_store("store2.com")
        assert store is not None
        assert store.point_rate == 10.0

        unknown = config.get_store("unknown.com")
        assert unknown is None

    def test_resolve_items(self):
        """アイテム解決"""
        data = {
            "store_list": [
                {"name": "yodobashi.com", "point_rate": 10.0},
            ],
            "item_list": [
                {"name": "Item 1", "store": "yodobashi.com", "url": "https://yodobashi.com/1"},
            ],
        }

        config = TargetConfig.parse(data)
        resolved = config.resolve_items()

        assert len(resolved) == 1
        assert resolved[0].name == "Item 1"
        assert resolved[0].point_rate == 10.0
