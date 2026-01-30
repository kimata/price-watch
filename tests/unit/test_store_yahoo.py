#!/usr/bin/env python3
# ruff: noqa: S101
"""
store/yahoo.py のユニットテスト

Yahoo!ショッピング検索による価格チェックを検証します。
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import my_lib.store.yahoo.api

import price_watch.models
import price_watch.store.yahoo
from price_watch.target import CheckMethod, ResolvedItem


def _create_resolved_item(
    name: str = "テスト商品",
    store: str = "Yahoo",
    search_keyword: str | None = None,
    jan_code: str | None = None,
    price_range: list[int] | None = None,
    cond: str | None = None,
) -> ResolvedItem:
    """テスト用の ResolvedItem を作成."""
    return ResolvedItem(
        name=name,
        store=store,
        url="",  # Yahoo は URL なしで OK
        check_method=CheckMethod.YAHOO_SEARCH,
        search_keyword=search_keyword,
        jan_code=jan_code,
        price_range=price_range,
        cond=cond,
    )


def _create_checked_item(
    name: str = "テスト商品",
    store: str = "Yahoo",
    search_keyword: str | None = None,
    search_cond: str | None = None,
) -> price_watch.models.CheckedItem:
    """テスト用の CheckedItem を作成."""
    return price_watch.models.CheckedItem(
        name=name,
        store=store,
        url=None,
        search_keyword=search_keyword,
        search_cond=search_cond,
    )


def _create_mock_config(with_yahoo_api: bool = True) -> MagicMock:
    """テスト用のモック設定を作成."""
    mock_config = MagicMock()
    if with_yahoo_api:
        mock_config.store.yahoo_api = MagicMock()
    else:
        mock_config.store.yahoo_api = None
    return mock_config


@dataclass
class MockSearchResult:
    """モック用の検索結果"""

    name: str
    price: int
    url: str
    thumb_url: str | None = None


class TestParseCond:
    """_parse_cond 関数のテスト"""

    def test_none_returns_new(self):
        """None は NEW を返す"""
        result = price_watch.store.yahoo._parse_cond(None)
        assert result == my_lib.store.yahoo.api.Condition.NEW

    def test_empty_string_returns_new(self):
        """空文字列は NEW を返す"""
        result = price_watch.store.yahoo._parse_cond("")
        assert result == my_lib.store.yahoo.api.Condition.NEW

    def test_new_returns_new(self):
        """ "new" は NEW を返す"""
        result = price_watch.store.yahoo._parse_cond("new")
        assert result == my_lib.store.yahoo.api.Condition.NEW

    def test_used_returns_used(self):
        """ "used" は USED を返す"""
        result = price_watch.store.yahoo._parse_cond("used")
        assert result == my_lib.store.yahoo.api.Condition.USED

    def test_case_insensitive(self):
        """大文字小文字を区別しない"""
        result = price_watch.store.yahoo._parse_cond("NEW")
        assert result == my_lib.store.yahoo.api.Condition.NEW

        result = price_watch.store.yahoo._parse_cond("Used")
        assert result == my_lib.store.yahoo.api.Condition.USED

    def test_with_whitespace(self):
        """前後の空白を除去"""
        result = price_watch.store.yahoo._parse_cond("  new  ")
        assert result == my_lib.store.yahoo.api.Condition.NEW

    def test_unknown_condition_warning(self):
        """不明な状態は警告して NEW を返す"""
        with patch("logging.warning") as mock_warn:
            result = price_watch.store.yahoo._parse_cond("unknown")

            mock_warn.assert_called_once()
            assert result == my_lib.store.yahoo.api.Condition.NEW


class TestBuildSearchCondition:
    """_build_search_condition 関数のテスト"""

    def test_basic_with_name(self):
        """名前から検索条件を作成"""
        item = _create_resolved_item(name="テスト商品")

        result = price_watch.store.yahoo._build_search_condition(item)

        assert result.keyword == "テスト商品"
        assert result.jan is None
        assert result.price_min is None
        assert result.price_max is None
        assert result.condition == my_lib.store.yahoo.api.Condition.NEW

    def test_with_search_keyword(self):
        """search_keyword 指定時は名前より優先"""
        item = _create_resolved_item(name="テスト商品", search_keyword="カスタムキーワード")

        result = price_watch.store.yahoo._build_search_condition(item)

        assert result.keyword == "カスタムキーワード"

    def test_with_jan_code(self):
        """JAN コード指定"""
        item = _create_resolved_item(name="テスト商品", jan_code="4901234567890")

        result = price_watch.store.yahoo._build_search_condition(item)

        assert result.keyword == "テスト商品"
        assert result.jan == "4901234567890"

    def test_with_price_range_single(self):
        """価格範囲（最小値のみ）"""
        item = _create_resolved_item(name="テスト商品", price_range=[1000])

        result = price_watch.store.yahoo._build_search_condition(item)

        assert result.price_min == 1000
        assert result.price_max is None

    def test_with_price_range_full(self):
        """価格範囲（最小・最大）"""
        item = _create_resolved_item(name="テスト商品", price_range=[1000, 5000])

        result = price_watch.store.yahoo._build_search_condition(item)

        assert result.price_min == 1000
        assert result.price_max == 5000

    def test_with_cond_used(self):
        """商品状態 USED"""
        item = _create_resolved_item(name="テスト商品", cond="used")

        result = price_watch.store.yahoo._build_search_condition(item)

        assert result.condition == my_lib.store.yahoo.api.Condition.USED


class TestBuildSearchCondJson:
    """_build_search_cond_json 関数のテスト"""

    def test_empty_condition(self):
        """空の検索条件"""
        condition = my_lib.store.yahoo.api.SearchCondition(
            keyword="テスト",
            jan=None,
            price_min=None,
            price_max=None,
            condition=my_lib.store.yahoo.api.Condition.NEW,
        )

        result = price_watch.store.yahoo._build_search_cond_json(condition)

        assert result == ""

    def test_with_jan(self):
        """JAN コード指定"""
        condition = my_lib.store.yahoo.api.SearchCondition(
            keyword="テスト",
            jan="4901234567890",
            price_min=None,
            price_max=None,
            condition=my_lib.store.yahoo.api.Condition.NEW,
        )

        result = price_watch.store.yahoo._build_search_cond_json(condition)

        assert '"jan": "4901234567890"' in result

    def test_with_price_range(self):
        """価格範囲"""
        condition = my_lib.store.yahoo.api.SearchCondition(
            keyword="テスト",
            jan=None,
            price_min=1000,
            price_max=5000,
            condition=my_lib.store.yahoo.api.Condition.NEW,
        )

        result = price_watch.store.yahoo._build_search_cond_json(condition)

        assert '"price_min": 1000' in result
        assert '"price_max": 5000' in result

    def test_with_used_condition(self):
        """USED 条件"""
        condition = my_lib.store.yahoo.api.SearchCondition(
            keyword="テスト",
            jan=None,
            price_min=None,
            price_max=None,
            condition=my_lib.store.yahoo.api.Condition.USED,
        )

        result = price_watch.store.yahoo._build_search_cond_json(condition)

        assert '"cond": "used"' in result

    def test_combined_conditions(self):
        """複合条件"""
        condition = my_lib.store.yahoo.api.SearchCondition(
            keyword="テスト",
            jan="4901234567890",
            price_min=1000,
            price_max=5000,
            condition=my_lib.store.yahoo.api.Condition.USED,
        )

        result = price_watch.store.yahoo._build_search_cond_json(condition)

        assert '"jan": "4901234567890"' in result
        assert '"price_min": 1000' in result
        assert '"price_max": 5000' in result
        assert '"cond": "used"' in result


class TestCheck:
    """check 関数のテスト"""

    def test_no_yahoo_api_config(self):
        """Yahoo API 設定がない場合は失敗"""
        mock_config = _create_mock_config(with_yahoo_api=False)
        item = _create_resolved_item(name="テスト商品")

        result = price_watch.store.yahoo.check(mock_config, item)

        assert result.crawl_status == price_watch.models.CrawlStatus.FAILURE

    def test_no_results(self):
        """検索結果なし"""
        mock_config = _create_mock_config()
        item = _create_resolved_item(name="テスト商品")

        with patch("my_lib.store.yahoo.api.search", return_value=[]):
            result = price_watch.store.yahoo.check(mock_config, item)

        assert result.stock == price_watch.models.StockStatus.OUT_OF_STOCK
        assert result.crawl_status == price_watch.models.CrawlStatus.SUCCESS

    def test_with_results(self):
        """検索結果あり"""
        mock_config = _create_mock_config()
        item = _create_resolved_item(name="テスト商品")

        mock_results = [
            MockSearchResult(
                name="テスト商品 A",
                price=2000,
                url="https://store.yahoo.co.jp/a",
                thumb_url="https://example.com/a.jpg",
            ),
            MockSearchResult(
                name="テスト商品 B", price=3000, url="https://store.yahoo.co.jp/b", thumb_url=None
            ),
        ]

        with patch("my_lib.store.yahoo.api.search", return_value=mock_results):
            result = price_watch.store.yahoo.check(mock_config, item)

        # 最初の商品（最安値）を選択
        assert result.url == "https://store.yahoo.co.jp/a"
        assert result.price == 2000
        # NOTE: Yahoo 検索結果のサムネイルは使用しない（検索のたびに別商品になる可能性があるため）
        assert result.thumb_url is None
        assert result.stock == price_watch.models.StockStatus.IN_STOCK
        assert result.crawl_status == price_watch.models.CrawlStatus.SUCCESS

    def test_api_exception(self):
        """API 例外"""
        mock_config = _create_mock_config()
        item = _create_resolved_item(name="テスト商品")

        with patch("my_lib.store.yahoo.api.search", side_effect=Exception("API Error")):
            result = price_watch.store.yahoo.check(mock_config, item)

        assert result.crawl_status == price_watch.models.CrawlStatus.FAILURE

    def test_search_keyword_set_for_keyword_search(self):
        """キーワード検索時は search_keyword が設定される"""
        mock_config = _create_mock_config()
        item = _create_resolved_item(name="テスト商品", search_keyword="カスタム")

        with patch("my_lib.store.yahoo.api.search", return_value=[]):
            result = price_watch.store.yahoo.check(mock_config, item)

        assert result.search_keyword == "カスタム"

    def test_search_keyword_set_for_jan_search(self):
        """JAN 検索時は search_keyword に JAN が設定される"""
        mock_config = _create_mock_config()
        item = _create_resolved_item(name="テスト商品", jan_code="4901234567890")

        with patch("my_lib.store.yahoo.api.search", return_value=[]):
            result = price_watch.store.yahoo.check(mock_config, item)

        assert result.search_keyword == "4901234567890"


class TestCheckKeywordFilter:
    """check 関数のキーワードフィルタリングテスト"""

    def test_filters_by_keyword(self):
        """キーワード不一致の商品が除外される"""
        mock_config = _create_mock_config()
        item = _create_resolved_item(name="テスト商品", search_keyword="MacBook Pro M4")

        mock_results = [
            MockSearchResult(name="MacBook Pro M4 14インチ", price=200000, url="https://store.yahoo.co.jp/a"),
            MockSearchResult(name="MacBook Air M4", price=150000, url="https://store.yahoo.co.jp/b"),
            MockSearchResult(name="MacBook Pro M4 16インチ", price=250000, url="https://store.yahoo.co.jp/c"),
        ]

        with patch("my_lib.store.yahoo.api.search", return_value=mock_results):
            result = price_watch.store.yahoo.check(mock_config, item)

        # Air は除外、Pro M4 の先頭（最安）が選択される
        assert result.url == "https://store.yahoo.co.jp/a"
        assert result.price == 200000
        assert result.stock == price_watch.models.StockStatus.IN_STOCK

    def test_all_filtered_out_by_keyword(self):
        """全商品がキーワードフィルタで除外された場合は OUT_OF_STOCK"""
        mock_config = _create_mock_config()
        item = _create_resolved_item(name="テスト商品", search_keyword="MacBook Pro M4")

        mock_results = [
            MockSearchResult(name="MacBook Air M4", price=150000, url="https://store.yahoo.co.jp/a"),
            MockSearchResult(name="iPad Pro M4", price=120000, url="https://store.yahoo.co.jp/b"),
        ]

        with patch("my_lib.store.yahoo.api.search", return_value=mock_results):
            result = price_watch.store.yahoo.check(mock_config, item)

        assert result.stock == price_watch.models.StockStatus.OUT_OF_STOCK
        assert result.crawl_status == price_watch.models.CrawlStatus.SUCCESS

    def test_jan_search_skips_keyword_filter(self):
        """JANコード検索時はキーワードフィルタをスキップ"""
        mock_config = _create_mock_config()
        item = _create_resolved_item(
            name="テスト商品",
            jan_code="4901234567890",
            search_keyword="特定キーワード",
        )

        mock_results = [
            MockSearchResult(name="全く違う商品名", price=5000, url="https://store.yahoo.co.jp/a"),
        ]

        with patch("my_lib.store.yahoo.api.search", return_value=mock_results):
            result = price_watch.store.yahoo.check(mock_config, item)

        # JAN 検索なのでフィルタされず、結果が返る
        assert result.url == "https://store.yahoo.co.jp/a"
        assert result.price == 5000
        assert result.stock == price_watch.models.StockStatus.IN_STOCK


class TestGenerateItemKey:
    """generate_item_key 関数のテスト"""

    def test_basic(self):
        """基本的なキー生成"""
        item = _create_checked_item(
            search_keyword="テスト",
            search_cond='{"jan": "4901234567890"}',
        )

        with patch("price_watch.history.generate_item_key", return_value="generated_key"):
            result = price_watch.store.yahoo.generate_item_key(item)

        assert result == "generated_key"

    def test_without_search_cond(self):
        """search_cond なし"""
        item = _create_checked_item(search_keyword="テスト")

        with patch("price_watch.history.generate_item_key", return_value="key"):
            result = price_watch.store.yahoo.generate_item_key(item)

        assert result == "key"
