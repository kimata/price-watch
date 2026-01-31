#!/usr/bin/env python3
# ruff: noqa: S101
"""
target.py のユニットテスト
"""

import pathlib
from unittest.mock import patch

import pytest

from price_watch.target import (
    ActionStep,
    ActionType,
    CheckMethod,
    ItemDefinition,
    PreloadConfig,
    ResolvedItem,
    StoreDefinition,
    TargetConfig,
    load,
)


class TestActionStep:
    """ActionStep のテスト"""

    def test_parse_click(self):
        """クリックアクションをパース"""
        data = {"type": "click", "xpath": "//button[@id='submit']"}
        step = ActionStep.parse(data)

        assert step.type == ActionType.CLICK
        assert step.xpath == "//button[@id='submit']"
        assert step.value is None

    def test_parse_input(self):
        """入力アクションをパース"""
        data = {"type": "input", "xpath": "//input[@name='code']", "value": "123456"}
        step = ActionStep.parse(data)

        assert step.type == ActionType.INPUT
        assert step.xpath == "//input[@name='code']"
        assert step.value == "123456"

    def test_parse_sixdigit(self):
        """6桁コードアクションをパース"""
        data = {"type": "sixdigit", "xpath": "//div[@class='captcha']"}
        step = ActionStep.parse(data)

        assert step.type == ActionType.SIXDIGIT

    def test_parse_recaptcha(self):
        """reCAPTCHAアクションをパース"""
        data = {"type": "recaptcha"}
        step = ActionStep.parse(data)

        assert step.type == ActionType.RECAPTCHA
        assert step.xpath is None


class TestPreloadConfig:
    """PreloadConfig のテスト"""

    def test_parse_with_url_only(self):
        """URL のみ指定"""
        data = {"url": "https://example.com/preload"}
        config = PreloadConfig.parse(data)

        assert config.url == "https://example.com/preload"
        assert config.every == 1

    def test_parse_with_every(self):
        """every を指定"""
        data = {"url": "https://example.com/preload", "every": 5}
        config = PreloadConfig.parse(data)

        assert config.url == "https://example.com/preload"
        assert config.every == 5


class TestCheckMethod:
    """CheckMethod のテスト"""

    def test_scrape_value(self):
        """SCRAPE の値"""
        assert CheckMethod.SCRAPE.value == "scrape"

    def test_amazon_paapi_value(self):
        """AMAZON_PAAPI の値"""
        assert CheckMethod.AMAZON_PAAPI.value == "my_lib.store.amazon.api"

    def test_mercari_search_value(self):
        """MERCARI_SEARCH の値"""
        assert CheckMethod.MERCARI_SEARCH.value == "my_lib.store.mercari.search"


class TestActionType:
    """ActionType のテスト"""

    def test_all_action_types(self):
        """全アクションタイプの値"""
        assert ActionType.CLICK.value == "click"
        assert ActionType.INPUT.value == "input"
        assert ActionType.SIXDIGIT.value == "sixdigit"
        assert ActionType.RECAPTCHA.value == "recaptcha"


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
            "check_method": "my_lib.store.amazon.api",
        }
        store = StoreDefinition.parse(data)

        assert store.check_method == CheckMethod.AMAZON_PAAPI

    def test_parse_with_mercari_search(self):
        """メルカリ検索メソッド付きパース"""
        data = {
            "name": "mercari",
            "check_method": "my_lib.store.mercari.search",
        }
        store = StoreDefinition.parse(data)

        assert store.check_method == CheckMethod.MERCARI_SEARCH

    def test_parse_with_backward_compat_amazon_paapi(self):
        """後方互換性: amazon-paapi をサポート"""
        data = {
            "name": "amazon.co.jp",
            "check_method": "amazon-paapi",
        }
        store = StoreDefinition.parse(data)

        assert store.check_method == CheckMethod.AMAZON_PAAPI

    def test_parse_with_actions(self):
        """アクション付きパース"""
        data = {
            "name": "store-with-captcha.com",
            "action": [
                {"type": "click", "xpath": "//button[@id='accept']"},
                {"type": "recaptcha"},
            ],
        }
        store = StoreDefinition.parse(data)

        assert len(store.actions) == 2
        assert store.actions[0].type == ActionType.CLICK
        assert store.actions[1].type == ActionType.RECAPTCHA

    def test_parse_raises_error_when_too_many_actions(self):
        """action が最大個数を超えたらエラー"""
        data = {
            "name": "store.com",
            "action": [{"type": "click", "xpath": f"//button{i}"} for i in range(11)],
        }
        with pytest.raises(ValueError, match="too many actions"):
            StoreDefinition.parse(data)

    def test_parse_with_max_actions(self):
        """action が最大個数ちょうどなら OK"""
        data = {
            "name": "store.com",
            "action": [{"type": "click", "xpath": f"//button{i}"} for i in range(10)],
        }
        store = StoreDefinition.parse(data)
        assert len(store.actions) == 10

    def test_parse_with_assumption_point_rate(self):
        """assumption.point_rate からポイント還元率を取得"""
        data = {
            "name": "store.com",
            "assumption": {"point_rate": 15.0},
        }
        store = StoreDefinition.parse(data)

        assert store.point_rate == 15.0

    def test_parse_with_all_xpaths(self):
        """全 XPath 設定付きパース"""
        data = {
            "name": "full-store.com",
            "price_xpath": "//span[@class='price']",
            "thumb_img_xpath": "//img[@id='main']/@src",
            "unavailable_xpath": "//div[text()='売り切れ']",
            "price_unit": "ドル",
            "color": "#ff9900",
        }
        store = StoreDefinition.parse(data)

        assert store.price_xpath == "//span[@class='price']"
        assert store.thumb_img_xpath == "//img[@id='main']/@src"
        assert store.unavailable_xpath == "//div[text()='売り切れ']"
        assert store.price_unit == "ドル"
        assert store.color == "#ff9900"

    def test_parse_with_affiliate_id(self):
        """アフィリエイトID付きパース"""
        data = {
            "name": "mercari",
            "check_method": "my_lib.store.mercari.search",
            "affiliate_id": "my_mercari_affiliate",
        }
        store = StoreDefinition.parse(data)

        assert store.affiliate_id == "my_mercari_affiliate"

    def test_parse_without_affiliate_id(self):
        """アフィリエイトIDなしパース（デフォルトはNone）"""
        data = {"name": "test-store.com"}
        store = StoreDefinition.parse(data)

        assert store.affiliate_id is None


class TestItemDefinition:
    """ItemDefinition のテスト"""

    def test_parse_basic(self):
        """基本的なパース"""
        data = {"name": "Test Item", "store": "store.com", "url": "https://store.com/item"}
        item = ItemDefinition.parse(data)

        assert item.name == "Test Item"
        assert item.store == "store.com"
        assert item.url == "https://store.com/item"
        assert item.preload is None

    def test_parse_with_preload(self):
        """プリロード設定付きパース"""
        data = {
            "name": "Test Item",
            "store": "store.com",
            "url": "https://store.com/item",
            "preload": {"url": "https://store.com/login", "every": 3},
        }
        item = ItemDefinition.parse(data)

        assert item.preload is not None
        assert item.preload.url == "https://store.com/login"
        assert item.preload.every == 3

    def test_parse_with_mercari_options(self):
        """メルカリ検索オプション付きパース"""
        data = {
            "name": "Nintendo Switch",
            "store": "mercari",
            "search_keyword": "スイッチ",
            "exclude_keyword": "ジャンク",
            "cond": "NEW|LIKE_NEW",
        }
        item = ItemDefinition.parse(data)

        assert item.search_keyword == "スイッチ"
        assert item.exclude_keyword == "ジャンク"
        assert item.cond == "NEW|LIKE_NEW"

    def test_parse_with_price_range_list(self):
        """価格範囲（リスト形式）付きパース"""
        data = {
            "name": "Item",
            "store": "mercari",
            "price": [1000, 5000],
        }
        item = ItemDefinition.parse(data)

        assert item.price_range == [1000, 5000]

    def test_parse_with_price_range_single(self):
        """価格範囲（単一値）付きパース"""
        data = {
            "name": "Item",
            "store": "mercari",
            "price": 3000,
        }
        item = ItemDefinition.parse(data)

        assert item.price_range == [3000]

    def test_parse_with_all_xpaths(self):
        """全 XPath オーバーライド付きパース"""
        data = {
            "name": "Custom Item",
            "store": "store.com",
            "url": "https://store.com/item",
            "price_xpath": "//custom[@class='price']",
            "thumb_img_xpath": "//custom[@class='img']",
            "unavailable_xpath": "//custom[@class='soldout']",
            "price_unit": "ユーロ",
        }
        item = ItemDefinition.parse(data)

        assert item.price_xpath == "//custom[@class='price']"
        assert item.thumb_img_xpath == "//custom[@class='img']"
        assert item.unavailable_xpath == "//custom[@class='soldout']"
        assert item.price_unit == "ユーロ"

    def test_parse_list_new_format_multiple_stores(self):
        """新書式: 複数ストアの展開"""
        data = {
            "name": "商品名",
            "store": [
                {"name": "amazon.co.jp", "asin": "B01MFGU3ZP"},
                {"name": "yodobashi.com", "url": "https://www.yodobashi.com/product/123"},
            ],
        }
        items = ItemDefinition.parse_list(data)

        assert len(items) == 2
        assert items[0].name == "商品名"
        assert items[0].store == "amazon.co.jp"
        assert items[0].asin == "B01MFGU3ZP"
        assert items[0].url is None
        assert items[1].name == "商品名"
        assert items[1].store == "yodobashi.com"
        assert items[1].url == "https://www.yodobashi.com/product/123"
        assert items[1].asin is None

    def test_parse_list_new_format_single_store(self):
        """新書式: 単一ストア"""
        data = {
            "name": "商品名",
            "store": [
                {"name": "mercari.com", "search_keyword": "キーワード", "price": [1000, 5000], "cond": "NEW"},
            ],
        }
        items = ItemDefinition.parse_list(data)

        assert len(items) == 1
        assert items[0].name == "商品名"
        assert items[0].store == "mercari.com"
        assert items[0].search_keyword == "キーワード"
        assert items[0].price_range == [1000, 5000]
        assert items[0].cond == "NEW"

    def test_parse_list_new_format_store_entry_attributes(self):
        """新書式: ストアエントリの全属性"""
        data = {
            "name": "商品名",
            "store": [
                {
                    "name": "store.com",
                    "url": "https://store.com/item",
                    "price_xpath": "//span[@class='price']",
                    "thumb_img_xpath": "//img[@id='main']",
                    "unavailable_xpath": "//div[text()='売切']",
                    "price_unit": "ドル",
                    "preload": {"url": "https://store.com/login", "every": 3},
                    "jan_code": "4901234567890",
                    "exclude_keyword": "ジャンク",
                },
            ],
        }
        items = ItemDefinition.parse_list(data)

        assert len(items) == 1
        item = items[0]
        assert item.url == "https://store.com/item"
        assert item.price_xpath == "//span[@class='price']"
        assert item.thumb_img_xpath == "//img[@id='main']"
        assert item.unavailable_xpath == "//div[text()='売切']"
        assert item.price_unit == "ドル"
        assert item.preload is not None
        assert item.preload.url == "https://store.com/login"
        assert item.preload.every == 3
        assert item.jan_code == "4901234567890"
        assert item.exclude_keyword == "ジャンク"

    def test_parse_list_item_level_price(self):
        """新書式: アイテムレベルの price が全ストアにフォールバック"""
        data = {
            "name": "商品名",
            "store": [
                {"name": "mercari.com"},
                {"name": "yahoo.co.jp"},
            ],
            "price": [5000, 10000],
        }
        items = ItemDefinition.parse_list(data)

        assert len(items) == 2
        assert items[0].price_range == [5000, 10000]
        assert items[1].price_range == [5000, 10000]

    def test_parse_list_item_level_price_overridden_by_store(self):
        """新書式: ストアエントリの price がアイテムレベルを上書き"""
        data = {
            "name": "商品名",
            "store": [
                {"name": "mercari.com", "price": [3000, 8000]},
                {"name": "yahoo.co.jp"},
            ],
            "price": [5000, 10000],
        }
        items = ItemDefinition.parse_list(data)

        assert items[0].price_range == [3000, 8000]
        assert items[1].price_range == [5000, 10000]

    def test_parse_list_item_level_cond(self):
        """新書式: アイテムレベルの cond が全ストアにフォールバック"""
        data = {
            "name": "商品名",
            "store": [
                {"name": "mercari.com"},
                {"name": "yahoo.co.jp"},
            ],
            "cond": "NEW|LIKE_NEW",
        }
        items = ItemDefinition.parse_list(data)

        assert items[0].cond == "NEW|LIKE_NEW"
        assert items[1].cond == "NEW|LIKE_NEW"

    def test_parse_list_item_level_cond_overridden_by_store(self):
        """新書式: ストアエントリの cond がアイテムレベルを上書き"""
        data = {
            "name": "商品名",
            "store": [
                {"name": "mercari.com", "cond": "NEW"},
                {"name": "yahoo.co.jp"},
            ],
            "cond": "NEW|LIKE_NEW",
        }
        items = ItemDefinition.parse_list(data)

        assert items[0].cond == "NEW"
        assert items[1].cond == "NEW|LIKE_NEW"

    def test_parse_list_old_format(self):
        """旧書式: store が文字列の場合は後方互換"""
        data = {
            "name": "Test Item",
            "store": "store.com",
            "url": "https://store.com/item",
        }
        items = ItemDefinition.parse_list(data)

        assert len(items) == 1
        assert items[0].name == "Test Item"
        assert items[0].store == "store.com"


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
                "check_method": "my_lib.store.amazon.api",
            }
        )

        resolved = ResolvedItem.from_item_and_store(item, store)

        assert resolved.asin == "B0123456789"
        assert resolved.url == "https://www.amazon.co.jp/dp/B0123456789"
        assert resolved.check_method == CheckMethod.AMAZON_PAAPI

    def test_from_item_without_url_raises_error(self):
        """URL も ASIN もない場合はエラー"""
        item = ItemDefinition.parse(
            {
                "name": "No URL Item",
                "store": "store.com",
            }
        )
        store = StoreDefinition.parse(
            {
                "name": "store.com",
            }
        )

        with pytest.raises(ValueError, match="has no url or asin"):
            ResolvedItem.from_item_and_store(item, store)

    def test_from_item_mercari_without_url(self):
        """メルカリ検索はURLなしでOK"""
        item = ItemDefinition.parse(
            {
                "name": "Mercari Item",
                "store": "mercari",
                "search_keyword": "キーワード",
            }
        )
        store = StoreDefinition.parse(
            {
                "name": "mercari",
                "check_method": "my_lib.store.mercari.search",
            }
        )

        resolved = ResolvedItem.from_item_and_store(item, store)

        # メルカリの場合は空文字列
        assert resolved.url == ""
        assert resolved.check_method == CheckMethod.MERCARI_SEARCH

    def test_from_item_with_affiliate_id(self):
        """アフィリエイトID付きストアからのマージ"""
        item = ItemDefinition.parse(
            {
                "name": "Mercari Item",
                "store": "mercari",
                "search_keyword": "キーワード",
            }
        )
        store = StoreDefinition.parse(
            {
                "name": "mercari",
                "check_method": "my_lib.store.mercari.search",
                "affiliate_id": "my_mercari_affiliate",
            }
        )

        resolved = ResolvedItem.from_item_and_store(item, store)

        assert resolved.affiliate_id == "my_mercari_affiliate"

    def test_amazon_url_with_affiliate_tag(self):
        """Amazon ASIN からURLを生成し、アフィリエイトタグを付与"""
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
                "check_method": "my_lib.store.amazon.api",
                "affiliate_id": "my-tag-22",
            }
        )

        resolved = ResolvedItem.from_item_and_store(item, store)

        assert resolved.url == "https://www.amazon.co.jp/dp/B0123456789?tag=my-tag-22"
        assert resolved.affiliate_id == "my-tag-22"

    def test_amazon_url_without_affiliate_tag(self):
        """Amazon ASIN からURLを生成（アフィリエイトIDなし）"""
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
                "check_method": "my_lib.store.amazon.api",
            }
        )

        resolved = ResolvedItem.from_item_and_store(item, store)

        assert resolved.url == "https://www.amazon.co.jp/dp/B0123456789"
        assert resolved.affiliate_id is None


class TestTargetConfig:
    """TargetConfig のテスト"""

    def test_parse_full(self):
        """完全なパース（旧書式）"""
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

    def test_parse_full_new_format(self):
        """完全なパース（新書式）"""
        data = {
            "store_list": [
                {"name": "store1.com", "point_rate": 5.0},
                {"name": "store2.com", "point_rate": 10.0},
            ],
            "item_list": [
                {
                    "name": "Item 1",
                    "store": [
                        {"name": "store1.com", "url": "https://store1.com/1"},
                        {"name": "store2.com", "url": "https://store2.com/2"},
                    ],
                },
            ],
        }

        config = TargetConfig.parse(data)

        assert len(config.stores) == 2
        assert len(config.items) == 2
        assert config.items[0].store == "store1.com"
        assert config.items[1].store == "store2.com"

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

    def test_resolve_items_new_format(self):
        """新書式でのアイテム解決"""
        data = {
            "store_list": [
                {"name": "amazon.co.jp", "check_method": "my_lib.store.amazon.api"},
                {"name": "yodobashi.com", "point_rate": 10.0},
            ],
            "item_list": [
                {
                    "name": "商品A",
                    "store": [
                        {"name": "amazon.co.jp", "asin": "B0123456789"},
                        {"name": "yodobashi.com", "url": "https://yodobashi.com/1"},
                    ],
                },
            ],
        }

        config = TargetConfig.parse(data)
        resolved = config.resolve_items()

        assert len(resolved) == 2
        assert resolved[0].name == "商品A"
        assert resolved[0].store == "amazon.co.jp"
        assert resolved[0].check_method == CheckMethod.AMAZON_PAAPI
        assert resolved[0].asin == "B0123456789"
        assert resolved[1].name == "商品A"
        assert resolved[1].store == "yodobashi.com"
        assert resolved[1].point_rate == 10.0

    def test_parse_empty(self):
        """空の設定をパース"""
        data: dict[str, list[dict[str, str]]] = {}

        config = TargetConfig.parse(data)

        assert config.stores == []
        assert config.items == []


class TestLoad:
    """load 関数のテスト"""

    def test_load_with_path(self, tmp_path: pathlib.Path):
        """ファイルパス指定で読み込み（旧書式）"""
        target_file = tmp_path / "target.yaml"
        target_file.write_text(
            """
store_list:
    - name: test-store.com
      point_rate: 5.0
item_list:
    - name: Test Item
      store: test-store.com
      url: https://test-store.com/item
"""
        )

        config = load(target_file)

        assert len(config.stores) == 1
        assert config.stores[0].name == "test-store.com"
        assert len(config.items) == 1
        assert config.items[0].name == "Test Item"

    def test_load_new_format(self, tmp_path: pathlib.Path):
        """新書式で読み込み"""
        target_file = tmp_path / "target.yaml"
        target_file.write_text(
            """
store_list:
    - name: amazon.co.jp
      check_method: my_lib.store.amazon.api
    - name: yodobashi.com
      point_rate: 10.0
item_list:
    - name: 商品名
      store:
        - name: amazon.co.jp
          asin: B0123456789
        - name: yodobashi.com
          url: https://yodobashi.com/product/123
"""
        )

        config = load(target_file)

        assert len(config.stores) == 2
        assert len(config.items) == 2
        assert config.items[0].name == "商品名"
        assert config.items[0].store == "amazon.co.jp"
        assert config.items[0].asin == "B0123456789"
        assert config.items[1].name == "商品名"
        assert config.items[1].store == "yodobashi.com"
        assert config.items[1].url == "https://yodobashi.com/product/123"

    def test_load_with_none_uses_default(self):
        """None の場合はデフォルトパスを使用"""
        mock_data = {
            "store_list": [{"name": "default-store.com"}],
            "item_list": [],
        }

        with patch("my_lib.config.load", return_value=mock_data):
            config = load(None)

            assert len(config.stores) == 1
            assert config.stores[0].name == "default-store.com"
