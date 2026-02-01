#!/usr/bin/env python3
# ruff: noqa: S101
"""
store/flea_market.py のユニットテスト

フリマ検索（メルカリ・ラクマ・PayPayフリマ）による価格チェックを検証します。
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import price_watch.models
import price_watch.store.flea_market
from price_watch.target import CheckMethod, ResolvedItem


def _create_resolved_item(
    name: str = "テスト商品",
    store: str = "mercari",
    search_keyword: str | None = None,
    exclude_keyword: str | None = None,
    price_range: list[int] | None = None,
    cond: str | None = None,
) -> ResolvedItem:
    """テスト用の ResolvedItem を作成."""
    return ResolvedItem(
        name=name,
        store=store,
        url="",  # メルカリは URL なしで OK
        check_method=CheckMethod.MERCARI_SEARCH,
        search_keyword=search_keyword,
        exclude_keyword=exclude_keyword,
        price_range=price_range,
        cond=cond,
    )


def _create_checked_item(
    name: str = "テスト商品",
    store: str = "mercari",
    search_keyword: str | None = None,
    search_cond: str | None = None,
) -> price_watch.models.CheckedItem:
    """テスト用の CheckedItem を作成."""
    item = price_watch.models.CheckedItem(
        name=name,
        store=store,
        url=None,
        search_keyword=search_keyword,
        search_cond=search_cond,
    )
    return item


@dataclass
class MockSearchResult:
    """モック用の検索結果"""

    name: str
    price: int
    url: str


class TestParseCond:
    """_parse_cond 関数のテスト"""

    def test_none_returns_default(self):
        """None はデフォルト（NEW, LIKE_NEW）を返す"""
        result = price_watch.store.flea_market._parse_cond(None)
        assert result is not None
        assert len(result) == 2
        assert result[0].name == "NEW"
        assert result[1].name == "LIKE_NEW"

    def test_empty_string_returns_default(self):
        """空文字列はデフォルト（NEW, LIKE_NEW）を返す"""
        result = price_watch.store.flea_market._parse_cond("")
        assert result is not None
        assert len(result) == 2
        assert result[0].name == "NEW"
        assert result[1].name == "LIKE_NEW"

    def test_single_condition(self):
        """単一の状態"""
        result = price_watch.store.flea_market._parse_cond("NEW")

        assert result is not None
        assert len(result) == 1
        assert result[0].name == "NEW"

    def test_multiple_conditions(self):
        """複数の状態"""
        result = price_watch.store.flea_market._parse_cond("NEW|LIKE_NEW|GOOD")

        assert result is not None
        assert len(result) == 3

    def test_case_insensitive(self):
        """大文字小文字を区別しない"""
        result = price_watch.store.flea_market._parse_cond("new|LIKE_NEW|Good")

        assert result is not None
        assert len(result) == 3

    def test_unknown_condition_warning(self):
        """不明な状態は警告"""
        with patch("logging.warning") as mock_warn:
            result = price_watch.store.flea_market._parse_cond("NEW|UNKNOWN")

            mock_warn.assert_called_once()
            assert result is not None
            assert len(result) == 1

    def test_all_unknown_returns_none(self):
        """全て不明な場合は None"""
        with patch("logging.warning"):
            result = price_watch.store.flea_market._parse_cond("UNKNOWN|INVALID")

        assert result is None


class TestBuildSearchCondition:
    """_build_search_condition 関数のテスト"""

    def test_basic(self):
        """基本的な検索条件"""
        item = _create_resolved_item(name="テスト商品")

        result = price_watch.store.flea_market._build_search_condition(item)

        assert result.keyword == "テスト商品"
        assert result.exclude_keyword is None
        assert result.price_min is None
        assert result.price_max is None

    def test_with_search_keyword(self):
        """検索キーワード指定"""
        item = _create_resolved_item(name="テスト商品", search_keyword="カスタムキーワード")

        result = price_watch.store.flea_market._build_search_condition(item)

        assert result.keyword == "カスタムキーワード"

    def test_with_exclude_keyword(self):
        """除外キーワード"""
        item = _create_resolved_item(name="テスト商品", exclude_keyword="ジャンク")

        result = price_watch.store.flea_market._build_search_condition(item)

        assert result.exclude_keyword == "ジャンク"

    def test_with_price_range_single(self):
        """価格範囲（最小値のみ）"""
        item = _create_resolved_item(name="テスト商品", price_range=[1000])

        result = price_watch.store.flea_market._build_search_condition(item)

        assert result.price_min == 1000
        assert result.price_max is None

    def test_with_price_range_full(self):
        """価格範囲（最小・最大）"""
        item = _create_resolved_item(name="テスト商品", price_range=[1000, 5000])

        result = price_watch.store.flea_market._build_search_condition(item)

        assert result.price_min == 1000
        assert result.price_max == 5000

    def test_with_cond(self):
        """商品状態"""
        item = _create_resolved_item(name="テスト商品", cond="NEW|LIKE_NEW")

        result = price_watch.store.flea_market._build_search_condition(item)

        assert result.condition is not None
        assert len(result.condition) == 2


class TestBuildSearchCondJson:
    """_build_search_cond_json 関数のテスト"""

    def test_empty_condition(self):
        """空の検索条件"""
        condition = MagicMock()
        condition.exclude_keyword = None
        condition.price_min = None
        condition.price_max = None
        condition.condition = None

        result = price_watch.store.flea_market._build_search_cond_json(condition)

        assert result == ""

    def test_with_exclude(self):
        """除外キーワード"""
        condition = MagicMock()
        condition.exclude_keyword = "ジャンク"
        condition.price_min = None
        condition.price_max = None
        condition.condition = None

        result = price_watch.store.flea_market._build_search_cond_json(condition)

        assert '"exclude": "ジャンク"' in result

    def test_with_price_range(self):
        """価格範囲"""
        condition = MagicMock()
        condition.exclude_keyword = None
        condition.price_min = 1000
        condition.price_max = 5000
        condition.condition = None

        result = price_watch.store.flea_market._build_search_cond_json(condition)

        assert '"price_min": 1000' in result
        assert '"price_max": 5000' in result

    def test_with_conditions(self):
        """商品状態"""
        mock_cond = MagicMock()
        mock_cond.value = "NEW"

        condition = MagicMock()
        condition.exclude_keyword = None
        condition.price_min = None
        condition.price_max = None
        condition.condition = [mock_cond]

        result = price_watch.store.flea_market._build_search_cond_json(condition)

        assert '"cond": ["NEW"]' in result


def _patch_store_search(check_method, mock_search):
    """_STORE_SEARCH_FUNCS の検索関数を mock に差し替えるコンテキストマネージャ."""
    original = price_watch.store.flea_market._STORE_SEARCH_FUNCS[check_method]
    patched = (mock_search, original[1])
    return patch.dict(
        price_watch.store.flea_market._STORE_SEARCH_FUNCS,
        {check_method: patched},
    )


class TestCheck:
    """check 関数のテスト"""

    def test_no_results(self):
        """検索結果なし"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        item = _create_resolved_item(name="テスト商品")

        mock_search = MagicMock(return_value=[])
        with _patch_store_search(CheckMethod.MERCARI_SEARCH, mock_search):
            result = price_watch.store.flea_market.check(mock_config, mock_driver, item)

        assert result.stock == price_watch.models.StockStatus.OUT_OF_STOCK
        assert result.crawl_status == price_watch.models.CrawlStatus.SUCCESS

    def test_with_results(self):
        """検索結果あり"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        item = _create_resolved_item(name="テスト商品")

        mock_results = [
            MockSearchResult(name="テスト商品 A", price=3000, url="https://mercari.com/a"),
            MockSearchResult(name="テスト商品 B", price=2000, url="https://mercari.com/b"),  # 最安
            MockSearchResult(name="テスト商品 C", price=4000, url="https://mercari.com/c"),
        ]

        mock_search = MagicMock(return_value=mock_results)
        with _patch_store_search(CheckMethod.MERCARI_SEARCH, mock_search):
            result = price_watch.store.flea_market.check(mock_config, mock_driver, item)

        # 最安値の商品を選択
        assert result.url == "https://mercari.com/b"
        assert result.price == 2000
        assert result.stock == price_watch.models.StockStatus.IN_STOCK
        assert result.crawl_status == price_watch.models.CrawlStatus.SUCCESS

    def test_filters_by_price_range(self):
        """価格範囲でフィルタリング"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        item = _create_resolved_item(name="テスト商品", price_range=[2000, 3500])

        mock_results = [
            MockSearchResult(name="テスト商品 A", price=1000, url="https://mercari.com/a"),  # 範囲外
            MockSearchResult(name="テスト商品 B", price=2500, url="https://mercari.com/b"),  # 範囲内
            MockSearchResult(name="テスト商品 C", price=5000, url="https://mercari.com/c"),  # 範囲外
        ]

        mock_search = MagicMock(return_value=mock_results)
        with _patch_store_search(CheckMethod.MERCARI_SEARCH, mock_search):
            result = price_watch.store.flea_market.check(mock_config, mock_driver, item)

        # 範囲内の商品のみ
        assert result.url == "https://mercari.com/b"
        assert result.price == 2500

    def test_no_results_after_filter(self):
        """フィルタリング後に結果なし"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        item = _create_resolved_item(name="テスト商品", price_range=[10000, 20000])

        mock_results = [
            MockSearchResult(name="商品A", price=1000, url="https://mercari.com/a"),
        ]

        mock_search = MagicMock(return_value=mock_results)
        with _patch_store_search(CheckMethod.MERCARI_SEARCH, mock_search):
            result = price_watch.store.flea_market.check(mock_config, mock_driver, item)

        assert result.stock == price_watch.models.StockStatus.OUT_OF_STOCK


class TestCheckKeywordFilter:
    """check 関数のキーワードフィルタリングテスト"""

    def test_filters_by_keyword(self):
        """キーワード不一致の商品が除外される"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        item = _create_resolved_item(name="テスト商品", search_keyword="MacBook Pro M4")

        mock_results = [
            MockSearchResult(name="MacBook Pro M4 14インチ", price=200000, url="https://mercari.com/a"),
            MockSearchResult(name="MacBook Air M4", price=150000, url="https://mercari.com/b"),  # Pro不一致
            MockSearchResult(name="MacBook Pro M4 16インチ", price=250000, url="https://mercari.com/c"),
        ]

        mock_search = MagicMock(return_value=mock_results)
        with _patch_store_search(CheckMethod.MERCARI_SEARCH, mock_search):
            result = price_watch.store.flea_market.check(mock_config, mock_driver, item)

        # MacBook Air は除外され、Pro M4 の最安値が選択される
        assert result.url == "https://mercari.com/a"
        assert result.price == 200000
        assert result.stock == price_watch.models.StockStatus.IN_STOCK

    def test_all_filtered_out_by_keyword(self):
        """全商品がキーワードフィルタで除外された場合は OUT_OF_STOCK"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        item = _create_resolved_item(name="テスト商品", search_keyword="MacBook Pro M4")

        mock_results = [
            MockSearchResult(name="MacBook Air M4", price=150000, url="https://mercari.com/a"),
            MockSearchResult(name="iPad Pro M4", price=120000, url="https://mercari.com/b"),
        ]

        mock_search = MagicMock(return_value=mock_results)
        with _patch_store_search(CheckMethod.MERCARI_SEARCH, mock_search):
            result = price_watch.store.flea_market.check(mock_config, mock_driver, item)

        assert result.stock == price_watch.models.StockStatus.OUT_OF_STOCK
        assert result.crawl_status == price_watch.models.CrawlStatus.SUCCESS


class TestCheckRakuma:
    """check 関数のラクマ検索テスト"""

    def test_rakuma_search_calls_correct_module(self):
        """ラクマ検索では正しい検索関数が呼ばれる"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        item = ResolvedItem(
            name="テスト商品",
            store="rakuma",
            url="",
            check_method=CheckMethod.RAKUMA_SEARCH,
        )

        mock_results = [
            MockSearchResult(name="テスト商品 A", price=1500, url="https://fril.jp/item/a"),
        ]

        mock_search = MagicMock(return_value=mock_results)
        with _patch_store_search(CheckMethod.RAKUMA_SEARCH, mock_search):
            result = price_watch.store.flea_market.check(mock_config, mock_driver, item)

        mock_search.assert_called_once()
        assert result.price == 1500
        assert result.url == "https://fril.jp/item/a"
        assert result.stock == price_watch.models.StockStatus.IN_STOCK


class TestCheckPayPay:
    """check 関数の PayPayフリマ検索テスト"""

    def test_paypay_search_calls_correct_module(self):
        """PayPay検索では正しい検索関数が呼ばれる"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        item = ResolvedItem(
            name="テスト商品",
            store="paypay",
            url="",
            check_method=CheckMethod.PAYPAY_SEARCH,
        )

        mock_results = [
            MockSearchResult(
                name="テスト商品 A", price=2500, url="https://paypayfleamarket.yahoo.co.jp/item/a"
            ),
        ]

        mock_search = MagicMock(return_value=mock_results)
        with _patch_store_search(CheckMethod.PAYPAY_SEARCH, mock_search):
            result = price_watch.store.flea_market.check(mock_config, mock_driver, item)

        mock_search.assert_called_once()
        assert result.price == 2500
        assert result.url == "https://paypayfleamarket.yahoo.co.jp/item/a"
        assert result.stock == price_watch.models.StockStatus.IN_STOCK


class TestCheckUnsupportedMethod:
    """check 関数の未対応チェックメソッドテスト"""

    def test_unsupported_method_returns_failure(self):
        """未対応のチェックメソッドでは FAILURE を返す"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        item = ResolvedItem(
            name="テスト商品",
            store="unknown",
            url="",
            check_method=CheckMethod.SCRAPE,  # フリマ検索ではないメソッド
        )

        result = price_watch.store.flea_market.check(mock_config, mock_driver, item)

        assert result.crawl_status == price_watch.models.CrawlStatus.FAILURE


class TestGenerateItemKey:
    """generate_item_key 関数のテスト"""

    def test_basic(self):
        """基本的なキー生成"""
        item = _create_checked_item(
            search_keyword="テスト",
            search_cond='{"exclude": "ジャンク"}',
        )

        with patch("price_watch.history.generate_item_key", return_value="generated_key"):
            result = price_watch.store.flea_market.generate_item_key(item)

        assert result == "generated_key"

    def test_without_search_cond(self):
        """search_cond なし"""
        item = _create_checked_item(search_keyword="テスト")

        with patch("price_watch.history.generate_item_key", return_value="key"):
            result = price_watch.store.flea_market.generate_item_key(item)

        assert result == "key"
