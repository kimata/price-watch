#!/usr/bin/env python3
# ruff: noqa: S101
"""
store/scrape.py のユニットテスト

スクレイピングによる価格チェックを検証します。
ブラウザ操作は my_lib.browser の Page 抽象（モック）経由で行います。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import price_watch.models
import price_watch.store.scrape
from price_watch.target import (
    ActionStep,
    ActionType,
    CheckMethod,
    PreloadConfig,
    ResolvedItem,
)


@pytest.fixture(autouse=True)
def _no_sleep():
    """スクレイピング処理中の待機（time.sleep）をスキップしてテストを高速化する。"""
    with patch("price_watch.store.scrape.time.sleep"):
        yield


def _create_resolved_item(
    name: str = "Test",
    store: str = "test-store.com",
    url: str = "https://example.com/item",
    price_xpath: str | None = None,
    thumb_img_xpath: str | None = None,
    unavailable_xpath: str | None = None,
    preload: PreloadConfig | None = None,
    actions: list[ActionStep] | None = None,
) -> ResolvedItem:
    """テスト用の ResolvedItem を作成."""
    return ResolvedItem(
        name=name,
        store=store,
        url=url,
        check_method=CheckMethod.SCRAPE,
        price_xpath=price_xpath,
        thumb_img_xpath=thumb_img_xpath,
        unavailable_xpath=unavailable_xpath,
        preload=preload,
        actions=actions if actions is not None else [],
    )


class TestResolveTemplate:
    """_resolve_template 関数のテスト"""

    def test_basic_substitution(self):
        """基本的な置換"""
        template = "検索: $item_name"
        item = _create_resolved_item(name="テスト商品")

        result = price_watch.store.scrape._resolve_template(template, item)

        assert result == "検索: テスト商品"

    def test_no_substitution(self):
        """置換なし"""
        template = "固定文字列"
        item = _create_resolved_item(name="テスト商品")

        result = price_watch.store.scrape._resolve_template(template, item)

        assert result == "固定文字列"

    def test_multiple_substitutions(self):
        """複数の置換"""
        template = "$item_name - $item_name"
        item = _create_resolved_item(name="商品A")

        result = price_watch.store.scrape._resolve_template(template, item)

        assert result == "商品A - 商品A"

    def test_missing_key_safe(self):
        """存在しないキーは安全に無視"""
        template = "$item_name - $other_key"
        item = _create_resolved_item(name="商品")

        result = price_watch.store.scrape._resolve_template(template, item)

        assert result == "商品 - $other_key"


class TestProcessAction:
    """_process_action 関数のテスト"""

    def test_click_action(self, make_page, make_element):
        """クリックアクションを処理"""
        mock_config = MagicMock()
        button = make_element()
        page = make_page(find={"//button": button})
        item = _create_resolved_item(actions=[ActionStep(type=ActionType.CLICK, xpath="//button")])

        price_watch.store.scrape._process_action(mock_config, page, item)

        button.click.assert_called_once()

    def test_click_element_not_found(self, make_page):
        """要素が見つからない場合は中断"""
        mock_config = MagicMock()
        page = make_page()  # find は常に None を返す
        item = _create_resolved_item(
            actions=[
                ActionStep(type=ActionType.CLICK, xpath="//button"),
                ActionStep(type=ActionType.CLICK, xpath="//other"),
            ]
        )

        price_watch.store.scrape._process_action(mock_config, page, item)

        # 最初の要素が見つからないので中断（find は 1 回だけ）
        assert page.find.call_count == 1

    def test_input_action(self, make_page, make_element):
        """入力アクションを処理"""
        mock_config = MagicMock()
        input_elem = make_element()
        page = make_page(find={"//input": input_elem})
        item = _create_resolved_item(
            actions=[ActionStep(type=ActionType.INPUT, xpath="//input", value="test_value")]
        )

        price_watch.store.scrape._process_action(mock_config, page, item)

        input_elem.type.assert_called_once_with("test_value")

    def test_recaptcha_action(self, make_page):
        """reCAPTCHA アクションを処理"""
        mock_config = MagicMock()
        page = make_page()
        item = _create_resolved_item(actions=[ActionStep(type=ActionType.RECAPTCHA)])

        with patch("price_watch.captcha.resolve_mp3") as mock_captcha:
            price_watch.store.scrape._process_action(mock_config, page, item)

        mock_captcha.assert_called_once_with(page)

    def test_click_action_xpath_none(self, make_page, make_element):
        """click アクションで xpath が None の場合はスキップ"""
        mock_config = MagicMock()
        button = make_element()
        page = make_page(find={"//button": button})
        item = _create_resolved_item(
            actions=[
                ActionStep(type=ActionType.CLICK, xpath=None),
                ActionStep(type=ActionType.CLICK, xpath="//button"),
            ]
        )

        price_watch.store.scrape._process_action(mock_config, page, item)

        # 2番目のアクションは実行される
        button.click.assert_called_once()

    def test_input_action_xpath_none(self, make_page, make_element):
        """input アクションで xpath が None の場合はスキップ"""
        mock_config = MagicMock()
        input_elem = make_element()
        page = make_page(find={"//input": input_elem})
        item = _create_resolved_item(
            actions=[
                ActionStep(type=ActionType.INPUT, xpath=None, value="test"),
                ActionStep(type=ActionType.INPUT, xpath="//input", value="test_value"),
            ]
        )

        price_watch.store.scrape._process_action(mock_config, page, item)

        # 2番目のアクションは実行される
        input_elem.type.assert_called_once_with("test_value")

    def test_input_action_element_not_found(self, make_page):
        """input アクションで要素が見つからない場合は中断"""
        mock_config = MagicMock()
        page = make_page()  # find は常に None
        item = _create_resolved_item(
            actions=[
                ActionStep(type=ActionType.INPUT, xpath="//input", value="test"),
                ActionStep(type=ActionType.INPUT, xpath="//other", value="test2"),
            ]
        )

        price_watch.store.scrape._process_action(mock_config, page, item)

        # 最初の要素が見つからないので中断（find は 1 回だけ）
        assert page.find.call_count == 1


class TestProcessPreload:
    """_process_preload 関数のテスト"""

    def test_no_preload(self, make_page):
        """プリロードなし"""
        mock_config = MagicMock()
        page = make_page()
        item = _create_resolved_item()

        price_watch.store.scrape._process_preload(mock_config, page, item, 0)

        # page.goto は呼ばれない
        page.goto.assert_not_called()

    def test_with_preload(self, make_page):
        """プリロードあり"""
        mock_config = MagicMock()
        page = make_page()
        item = _create_resolved_item(preload=PreloadConfig(url="https://example.com/preload", every=1))

        price_watch.store.scrape._process_preload(mock_config, page, item, 0)

        page.goto.assert_called_once_with("https://example.com/preload")

    def test_skip_by_every(self, make_page):
        """every 設定でスキップ"""
        mock_config = MagicMock()
        page = make_page()
        item = _create_resolved_item(preload=PreloadConfig(url="https://example.com/preload", every=3))

        # loop=1 は 3 で割り切れないのでスキップ
        price_watch.store.scrape._process_preload(mock_config, page, item, 1)

        page.goto.assert_not_called()

    def test_run_on_every(self, make_page):
        """every に合致する場合は実行"""
        mock_config = MagicMock()
        page = make_page()
        item = _create_resolved_item(preload=PreloadConfig(url="https://example.com/preload", every=3))

        # loop=3 は 3 で割り切れるので実行
        price_watch.store.scrape._process_preload(mock_config, page, item, 3)

        page.goto.assert_called_once()


class TestParseXpathAttr:
    """_parse_xpath_attr 関数のテスト"""

    def test_with_attr(self):
        """属性指定ありの XPath"""
        elem, attr = price_watch.store.scrape._parse_xpath_attr('//input[@class="largeUrl"]/@value')
        assert elem == '//input[@class="largeUrl"]'
        assert attr == "value"

    def test_with_src_attr(self):
        """src 属性指定ありの XPath"""
        elem, attr = price_watch.store.scrape._parse_xpath_attr("//img/@src")
        assert elem == "//img"
        assert attr == "src"

    def test_without_attr(self):
        """属性指定なしの XPath（デフォルト src）"""
        elem, attr = price_watch.store.scrape._parse_xpath_attr('//img[@id="mainImg"]')
        assert elem == '//img[@id="mainImg"]'
        assert attr == "src"


class TestCheckImpl:
    """_check_impl 関数のテスト"""

    def test_price_xpath_none(self, make_page):
        """price_xpath が None の場合"""
        mock_config = MagicMock()
        page = make_page()
        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath=None,
        )

        result = price_watch.store.scrape._check_impl(mock_config, page, item, 0)

        assert result.crawl_status == price_watch.models.CrawlStatus.FAILURE
        assert result.price is None

    def test_price_element_not_found(self, make_page):
        """価格要素が見つからない場合"""
        mock_config = MagicMock()
        page = make_page(exists=lambda _v: False)
        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
        )

        with patch("my_lib.browser.helpers.dump_page"):
            result = price_watch.store.scrape._check_impl(mock_config, page, item, 0)

        assert result.crawl_status == price_watch.models.CrawlStatus.FAILURE
        assert result.price is None

    def test_price_element_not_found_but_unavailable_detected(self, make_page, make_element):
        """価格要素が見つからないが unavailable_xpath がマッチする場合（販売終了など）"""
        mock_config = MagicMock()
        page = make_page(
            exists=lambda _v: False,
            find_all={"unavailable": [make_element()]},
        )
        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
            unavailable_xpath="//unavailable",
        )

        result = price_watch.store.scrape._check_impl(mock_config, page, item, 0)

        # 在庫なしとして SUCCESS 扱い
        assert result.crawl_status == price_watch.models.CrawlStatus.SUCCESS
        assert result.stock == price_watch.models.StockStatus.OUT_OF_STOCK
        assert result.price is None

    def test_price_element_not_found_unavailable_not_matched(self, make_page):
        """価格要素が見つからず unavailable_xpath もマッチしない場合"""
        mock_config = MagicMock()
        page = make_page(exists=lambda _v: False, find_all={"unavailable": []})
        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
            unavailable_xpath="//unavailable",
        )

        with patch("my_lib.browser.helpers.dump_page"):
            result = price_watch.store.scrape._check_impl(mock_config, page, item, 0)

        # FAILURE 扱い
        assert result.crawl_status == price_watch.models.CrawlStatus.FAILURE
        assert result.price is None

    def test_price_found_with_stock(self, make_page, make_element):
        """価格取得成功・在庫あり"""
        mock_config = MagicMock()
        price_elem = make_element(text="1,234円", visible=True)
        page = make_page(
            exists=lambda _v: True,
            find_all={"unavailable": [], "price": [price_elem]},
        )
        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
            unavailable_xpath="//unavailable",
        )

        result = price_watch.store.scrape._check_impl(mock_config, page, item, 0)

        assert result.crawl_status == price_watch.models.CrawlStatus.SUCCESS
        assert result.price == 1234
        assert result.stock == price_watch.models.StockStatus.IN_STOCK

    def test_price_found_without_stock(self, make_page, make_element):
        """価格取得成功・在庫なし"""
        mock_config = MagicMock()
        price_elem = make_element(text="在庫切れ", visible=True)
        page = make_page(
            exists=lambda _v: True,
            find_all={"unavailable": [make_element()], "price": [price_elem]},
        )
        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
            unavailable_xpath="//unavailable",
        )

        result = price_watch.store.scrape._check_impl(mock_config, page, item, 0)

        assert result.crawl_status == price_watch.models.CrawlStatus.SUCCESS
        assert result.price is None  # 在庫なしなので価格は設定されない
        assert result.stock == price_watch.models.StockStatus.OUT_OF_STOCK

    def test_no_unavailable_xpath_assumes_in_stock(self, make_page, make_element):
        """unavailable_xpath がない場合は在庫ありと仮定"""
        mock_config = MagicMock()
        price_elem = make_element(text="5,000円", visible=True)
        page = make_page(exists=lambda _v: True, find_all={"price": [price_elem]})
        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
        )

        result = price_watch.store.scrape._check_impl(mock_config, page, item, 0)

        assert result.crawl_status == price_watch.models.CrawlStatus.SUCCESS
        assert result.price == 5000
        assert result.stock == price_watch.models.StockStatus.IN_STOCK

    def test_with_action(self, make_page, make_element):
        """アクションありの場合"""
        mock_config = MagicMock()
        price_elem = make_element(text="1,000円", visible=True)
        page = make_page(exists=lambda _v: True, find_all={"price": [price_elem]})
        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
            actions=[ActionStep(type=ActionType.CLICK, xpath="//button")],
        )

        with patch("price_watch.store.scrape._process_action") as mock_action:
            result = price_watch.store.scrape._check_impl(mock_config, page, item, 0)

        mock_action.assert_called_once()
        assert result.price == 1000

    def test_thumbnail_from_img_xpath(self, make_page, make_element):
        """サムネイル画像の取得（img xpath）"""
        mock_config = MagicMock()
        price_elem = make_element(text="1,000円", visible=True)
        thumb_elem = make_element(attrs={"src": "/images/thumb.jpg"})
        page = make_page(
            exists=lambda _v: True,
            find_all={"price": [price_elem]},
            find={"img": thumb_elem},
        )
        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
            thumb_img_xpath="//img/@src",
        )

        with patch("price_watch.thumbnail.save_thumb", return_value="/local/thumb.jpg"):
            result = price_watch.store.scrape._check_impl(mock_config, page, item, 0)

        assert result.thumb_url == "/local/thumb.jpg"

    def test_price_parse_error_with_stock(self, make_page, make_element):
        """価格パースエラー（在庫あり）の場合は例外"""
        mock_config = MagicMock()
        price_elem = make_element(text="価格未定", visible=True)
        page = make_page(
            exists=lambda _v: True,
            find_all={"unavailable": [], "price": [price_elem]},
        )
        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
            unavailable_xpath="//unavailable",
        )

        with pytest.raises(ValueError, match="Invalid price format"):
            price_watch.store.scrape._check_impl(mock_config, page, item, 0)


class TestCheck:
    """check 関数のテスト"""

    def test_calls_check_impl(self, make_page):
        """_check_impl を呼び出して結果を返す"""
        mock_config = MagicMock()
        page = make_page()
        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
        )
        expected_result = price_watch.models.CheckedItem.from_resolved_item(item)

        with patch("price_watch.store.scrape._check_impl", return_value=expected_result):
            result = price_watch.store.scrape.check(mock_config, page, item, 0)

        assert result == expected_result

    def test_error_calls_notify_and_reraises(self, make_page):
        """エラー発生時に notify.error_with_page が呼ばれ、例外が再送出される"""
        mock_config = MagicMock()
        page = make_page()
        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
        )

        with (
            patch("price_watch.store.scrape._check_impl", side_effect=Exception("Test error")),
            patch("price_watch.notify.error_with_page") as mock_notify,
            pytest.raises(Exception, match="Test error"),
        ):
            price_watch.store.scrape.check(mock_config, page, item, 0)

        mock_notify.assert_called_once()
