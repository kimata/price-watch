#!/usr/bin/env python3
# ruff: noqa: S101
"""
store/scrape.py のユニットテスト

スクレイピングによる価格チェックを検証します。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import price_watch.models
import price_watch.store.scrape
from price_watch.target import (
    ActionStep,
    ActionType,
    CheckMethod,
    PreloadConfig,
    ResolvedItem,
)


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

    def test_click_action(self):
        """クリックアクションを処理"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = _create_resolved_item(actions=[ActionStep(type=ActionType.CLICK, xpath="//button")])

        with patch("my_lib.selenium_util.xpath_exists", return_value=True):
            price_watch.store.scrape._process_action(mock_config, mock_driver, mock_wait, item)

        # find_element と click が呼ばれた
        mock_driver.find_element.assert_called()

    def test_click_element_not_found(self):
        """要素が見つからない場合は中断"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = _create_resolved_item(
            actions=[
                ActionStep(type=ActionType.CLICK, xpath="//button"),
                ActionStep(type=ActionType.CLICK, xpath="//other"),
            ]
        )

        with patch("my_lib.selenium_util.xpath_exists", return_value=False):
            price_watch.store.scrape._process_action(mock_config, mock_driver, mock_wait, item)

        # 最初の要素が見つからないので中断
        mock_driver.find_element.assert_not_called()

    def test_input_action(self):
        """入力アクションを処理"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = _create_resolved_item(
            actions=[ActionStep(type=ActionType.INPUT, xpath="//input", value="test_value")]
        )

        with patch("my_lib.selenium_util.xpath_exists", return_value=True):
            price_watch.store.scrape._process_action(mock_config, mock_driver, mock_wait, item)

        # find_element が呼ばれた
        mock_driver.find_element.assert_called()

    def test_recaptcha_action(self):
        """reCAPTCHA アクションを処理"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = _create_resolved_item(actions=[ActionStep(type=ActionType.RECAPTCHA)])

        with patch("price_watch.captcha.resolve_mp3") as mock_captcha:
            price_watch.store.scrape._process_action(mock_config, mock_driver, mock_wait, item)

        mock_captcha.assert_called_once_with(mock_driver, mock_wait)

    def test_click_action_xpath_none(self):
        """click アクションで xpath が None の場合はスキップ"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = _create_resolved_item(
            actions=[
                ActionStep(type=ActionType.CLICK, xpath=None),
                ActionStep(type=ActionType.CLICK, xpath="//button"),
            ]
        )

        with patch("my_lib.selenium_util.xpath_exists", return_value=True):
            price_watch.store.scrape._process_action(mock_config, mock_driver, mock_wait, item)

        # 2番目のアクションは実行される
        mock_driver.find_element.assert_called()

    def test_input_action_xpath_none(self):
        """input アクションで xpath が None の場合はスキップ"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = _create_resolved_item(
            actions=[
                ActionStep(type=ActionType.INPUT, xpath=None, value="test"),
                ActionStep(type=ActionType.INPUT, xpath="//input", value="test_value"),
            ]
        )

        with patch("my_lib.selenium_util.xpath_exists", return_value=True):
            price_watch.store.scrape._process_action(mock_config, mock_driver, mock_wait, item)

        # 2番目のアクションは実行される
        mock_driver.find_element.assert_called()

    def test_input_action_element_not_found(self):
        """input アクションで要素が見つからない場合は中断"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = _create_resolved_item(
            actions=[
                ActionStep(type=ActionType.INPUT, xpath="//input", value="test"),
                ActionStep(type=ActionType.INPUT, xpath="//other", value="test2"),
            ]
        )

        with patch("my_lib.selenium_util.xpath_exists", return_value=False):
            price_watch.store.scrape._process_action(mock_config, mock_driver, mock_wait, item)

        # 最初の要素が見つからないので中断
        mock_driver.find_element.assert_not_called()


class TestProcessPreload:
    """_process_preload 関数のテスト"""

    def test_no_preload(self):
        """プリロードなし"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = _create_resolved_item()

        price_watch.store.scrape._process_preload(mock_config, mock_driver, mock_wait, item, 0)

        # driver.get は呼ばれない
        mock_driver.get.assert_not_called()

    def test_with_preload(self):
        """プリロードあり"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = _create_resolved_item(preload=PreloadConfig(url="https://example.com/preload", every=1))

        price_watch.store.scrape._process_preload(mock_config, mock_driver, mock_wait, item, 0)

        mock_driver.get.assert_called_once_with("https://example.com/preload")

    def test_skip_by_every(self):
        """every 設定でスキップ"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = _create_resolved_item(preload=PreloadConfig(url="https://example.com/preload", every=3))

        # loop=1 は 3 で割り切れないのでスキップ
        price_watch.store.scrape._process_preload(mock_config, mock_driver, mock_wait, item, 1)

        mock_driver.get.assert_not_called()

    def test_run_on_every(self):
        """every に合致する場合は実行"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = _create_resolved_item(preload=PreloadConfig(url="https://example.com/preload", every=3))

        # loop=3 は 3 で割り切れるので実行
        price_watch.store.scrape._process_preload(mock_config, mock_driver, mock_wait, item, 3)

        mock_driver.get.assert_called_once()


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

    def test_price_xpath_none(self):
        """price_xpath が None の場合"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"
        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath=None,
        )

        result = price_watch.store.scrape._check_impl(mock_config, mock_driver, item, 0)

        assert result.crawl_status == price_watch.models.CrawlStatus.FAILURE
        assert result.price is None

    def test_price_element_not_found(self):
        """価格要素が見つからない場合"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"
        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
        )

        with (
            patch("my_lib.selenium_util.xpath_exists", return_value=False),
            patch("my_lib.selenium_util.dump_page"),
        ):
            result = price_watch.store.scrape._check_impl(mock_config, mock_driver, item, 0)

        assert result.crawl_status == price_watch.models.CrawlStatus.FAILURE
        assert result.price is None

    def test_price_element_not_found_but_unavailable_detected(self):
        """価格要素が見つからないが unavailable_xpath がマッチする場合（販売終了など）"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"

        # unavailable_xpath がマッチするようにモック
        mock_unavailable_elem = MagicMock()
        mock_driver.find_elements.return_value = [mock_unavailable_elem]

        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
            unavailable_xpath='//p[contains(., "販売を終了しました")]',
        )

        with patch("my_lib.selenium_util.xpath_exists", return_value=False):
            result = price_watch.store.scrape._check_impl(mock_config, mock_driver, item, 0)

        # 在庫なしとして SUCCESS 扱い
        assert result.crawl_status == price_watch.models.CrawlStatus.SUCCESS
        assert result.stock == price_watch.models.StockStatus.OUT_OF_STOCK
        assert result.price is None

    def test_price_element_not_found_unavailable_not_matched(self):
        """価格要素が見つからず unavailable_xpath もマッチしない場合"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"

        # unavailable_xpath がマッチしないようにモック
        mock_driver.find_elements.return_value = []

        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
            unavailable_xpath='//p[contains(., "販売を終了しました")]',
        )

        with (
            patch("my_lib.selenium_util.xpath_exists", return_value=False),
            patch("my_lib.selenium_util.dump_page"),
        ):
            result = price_watch.store.scrape._check_impl(mock_config, mock_driver, item, 0)

        # FAILURE 扱い
        assert result.crawl_status == price_watch.models.CrawlStatus.FAILURE
        assert result.price is None

    def test_price_found_with_stock(self):
        """価格取得成功・在庫あり"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"

        mock_price_elem = MagicMock()
        mock_price_elem.text = "1,234円"
        mock_price_elem.is_displayed.return_value = True

        def find_elements_side_effect(_by, xpath):
            if "price" in xpath:
                return [mock_price_elem]
            return []  # unavailable なし

        mock_driver.find_elements.side_effect = find_elements_side_effect

        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
            unavailable_xpath="//unavailable",
        )

        with patch("my_lib.selenium_util.xpath_exists", return_value=True):
            result = price_watch.store.scrape._check_impl(mock_config, mock_driver, item, 0)

        assert result.crawl_status == price_watch.models.CrawlStatus.SUCCESS
        assert result.price == 1234
        assert result.stock == price_watch.models.StockStatus.IN_STOCK

    def test_price_found_without_stock(self):
        """価格取得成功・在庫なし"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"

        mock_price_elem = MagicMock()
        mock_price_elem.text = "在庫切れ"
        mock_price_elem.is_displayed.return_value = True

        def find_elements_side_effect(_by, xpath):
            if "price" in xpath:
                return [mock_price_elem]
            # unavailable_xpath がマッチ
            return [MagicMock()]

        mock_driver.find_elements.side_effect = find_elements_side_effect

        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
            unavailable_xpath="//unavailable",
        )

        with patch("my_lib.selenium_util.xpath_exists", return_value=True):
            result = price_watch.store.scrape._check_impl(mock_config, mock_driver, item, 0)

        assert result.crawl_status == price_watch.models.CrawlStatus.SUCCESS
        assert result.price is None  # 在庫なしなので価格は設定されない
        assert result.stock == price_watch.models.StockStatus.OUT_OF_STOCK

    def test_no_unavailable_xpath_assumes_in_stock(self):
        """unavailable_xpath がない場合は在庫ありと仮定"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"

        mock_price_elem = MagicMock()
        mock_price_elem.text = "5,000円"
        mock_price_elem.is_displayed.return_value = True
        mock_driver.find_elements.return_value = [mock_price_elem]

        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
        )

        with patch("my_lib.selenium_util.xpath_exists", return_value=True):
            result = price_watch.store.scrape._check_impl(mock_config, mock_driver, item, 0)

        assert result.crawl_status == price_watch.models.CrawlStatus.SUCCESS
        assert result.price == 5000
        assert result.stock == price_watch.models.StockStatus.IN_STOCK

    def test_with_action(self):
        """アクションありの場合"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"

        mock_price_elem = MagicMock()
        mock_price_elem.text = "1,000円"
        mock_price_elem.is_displayed.return_value = True
        mock_driver.find_elements.return_value = [mock_price_elem]

        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
            actions=[ActionStep(type=ActionType.CLICK, xpath="//button")],
        )

        with (
            patch("my_lib.selenium_util.xpath_exists", return_value=True),
            patch("price_watch.store.scrape._process_action") as mock_action,
        ):
            result = price_watch.store.scrape._check_impl(mock_config, mock_driver, item, 0)

        mock_action.assert_called_once()
        assert result.price == 1000

    def test_thumbnail_from_img_xpath(self):
        """サムネイル画像の取得（img xpath）"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"

        mock_price_elem = MagicMock()
        mock_price_elem.text = "1,000円"
        mock_price_elem.is_displayed.return_value = True

        mock_thumb_elem = MagicMock()
        mock_thumb_elem.get_attribute.return_value = "/images/thumb.jpg"

        def find_element(_by, xpath):
            if "img" in xpath:
                return mock_thumb_elem
            return mock_price_elem

        mock_driver.find_element.side_effect = find_element
        mock_driver.find_elements.return_value = [mock_price_elem]

        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
            thumb_img_xpath="//img/@src",
        )

        with (
            patch("my_lib.selenium_util.xpath_exists", return_value=True),
            patch("price_watch.thumbnail.save_thumb", return_value="/local/thumb.jpg"),
        ):
            result = price_watch.store.scrape._check_impl(mock_config, mock_driver, item, 0)

        assert result.thumb_url == "/local/thumb.jpg"

    def test_price_parse_error_with_stock(self):
        """価格パースエラー（在庫あり）の場合は例外"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"

        mock_price_elem = MagicMock()
        mock_price_elem.text = "価格未定"
        mock_price_elem.is_displayed.return_value = True

        def find_elements_side_effect(_by, xpath):
            if "price" in xpath:
                return [mock_price_elem]
            return []  # unavailable なし

        mock_driver.find_elements.side_effect = find_elements_side_effect

        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
            unavailable_xpath="//unavailable",
        )

        with patch("my_lib.selenium_util.xpath_exists", return_value=True):
            import pytest

            with pytest.raises(ValueError, match="Invalid price format"):
                price_watch.store.scrape._check_impl(mock_config, mock_driver, item, 0)


class TestCheck:
    """check 関数のテスト"""

    def test_calls_check_impl_with_error_handler(self):
        """error_handler 経由で _check_impl を呼び出す"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com"
        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
        )
        expected_result = price_watch.models.CheckedItem.from_resolved_item(item)

        with patch("price_watch.store.scrape._check_impl") as mock_impl:
            mock_impl.return_value = expected_result

            with patch("my_lib.selenium_util.error_handler") as mock_handler:
                # コンテキストマネージャーをモック
                mock_handler.return_value.__enter__ = MagicMock(return_value=None)
                mock_handler.return_value.__exit__ = MagicMock(return_value=False)

                result = price_watch.store.scrape.check(mock_config, mock_driver, item, 0)

        assert result == expected_result

    def test_error_handler_calls_notify_on_error(self):
        """エラー発生時に notify.error_with_page が呼ばれる"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com"
        item = _create_resolved_item(
            url="https://example.com/item",
            price_xpath="//price",
        )
        expected_result = price_watch.models.CheckedItem.from_resolved_item(item)

        # on_error コールバックをキャプチャ
        captured_on_error = None

        def capture_handler(*args, **kwargs):
            nonlocal captured_on_error
            captured_on_error = kwargs.get("on_error")
            # 正常終了するコンテキストマネージャーを返す
            mock_cm = MagicMock()
            mock_cm.__enter__ = MagicMock(return_value=None)
            mock_cm.__exit__ = MagicMock(return_value=False)
            return mock_cm

        with (
            patch("price_watch.store.scrape._check_impl") as mock_impl,
            patch("my_lib.selenium_util.error_handler", side_effect=capture_handler),
            patch("price_watch.notify.error_with_page") as mock_notify,
        ):
            mock_impl.return_value = expected_result
            price_watch.store.scrape.check(mock_config, mock_driver, item, 0)

            # on_error コールバックを実行
            if captured_on_error:
                test_exc = Exception("Test error")
                captured_on_error(test_exc, None, None)

        mock_notify.assert_called_once()
