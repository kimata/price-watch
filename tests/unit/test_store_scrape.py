#!/usr/bin/env python3
# ruff: noqa: S101
"""
store/scrape.py のユニットテスト

スクレイピングによる価格チェックを検証します。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import price_watch.store.scrape


class TestResolveTemplate:
    """_resolve_template 関数のテスト"""

    def test_basic_substitution(self):
        """基本的な置換"""
        template = "検索: $item_name"
        item = {"name": "テスト商品"}

        result = price_watch.store.scrape._resolve_template(template, item)

        assert result == "検索: テスト商品"

    def test_no_substitution(self):
        """置換なし"""
        template = "固定文字列"
        item = {"name": "テスト商品"}

        result = price_watch.store.scrape._resolve_template(template, item)

        assert result == "固定文字列"

    def test_multiple_substitutions(self):
        """複数の置換"""
        template = "$item_name - $item_name"
        item = {"name": "商品A"}

        result = price_watch.store.scrape._resolve_template(template, item)

        assert result == "商品A - 商品A"

    def test_missing_key_safe(self):
        """存在しないキーは安全に無視"""
        template = "$item_name - $other_key"
        item = {"name": "商品"}

        result = price_watch.store.scrape._resolve_template(template, item)

        assert result == "商品 - $other_key"


class TestProcessAction:
    """_process_action 関数のテスト"""

    def test_click_action(self):
        """クリックアクションを処理"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = {"name": "Test"}
        action_list = [{"type": "click", "xpath": "//button"}]

        with patch("my_lib.selenium_util.xpath_exists", return_value=True):
            price_watch.store.scrape._process_action(mock_config, mock_driver, mock_wait, item, action_list)

        # find_element と click が呼ばれた
        mock_driver.find_element.assert_called()

    def test_click_element_not_found(self):
        """要素が見つからない場合は中断"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = {"name": "Test"}
        action_list = [{"type": "click", "xpath": "//button"}, {"type": "click", "xpath": "//other"}]

        with patch("my_lib.selenium_util.xpath_exists", return_value=False):
            price_watch.store.scrape._process_action(mock_config, mock_driver, mock_wait, item, action_list)

        # 最初の要素が見つからないので中断
        mock_driver.find_element.assert_not_called()

    def test_input_action(self):
        """入力アクションを処理"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = {"name": "Test"}
        action_list = [{"type": "input", "xpath": "//input", "value": "test_value"}]

        with patch("my_lib.selenium_util.xpath_exists", return_value=True):
            price_watch.store.scrape._process_action(mock_config, mock_driver, mock_wait, item, action_list)

        # find_element が呼ばれた
        mock_driver.find_element.assert_called()

    def test_recaptcha_action(self):
        """reCAPTCHA アクションを処理"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = {"name": "Test"}
        action_list = [{"type": "recaptcha"}]

        with patch("price_watch.captcha.resolve_mp3") as mock_captcha:
            price_watch.store.scrape._process_action(mock_config, mock_driver, mock_wait, item, action_list)

        mock_captcha.assert_called_once_with(mock_driver, mock_wait)


class TestProcessPreload:
    """_process_preload 関数のテスト"""

    def test_no_preload(self):
        """プリロードなし"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = {"name": "Test"}

        price_watch.store.scrape._process_preload(mock_config, mock_driver, mock_wait, item, 0)

        # driver.get は呼ばれない
        mock_driver.get.assert_not_called()

    def test_with_preload(self):
        """プリロードあり"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = {
            "name": "Test",
            "preload": {
                "url": "https://example.com/preload",
                "every": 1,
                "action": [],
            },
        }

        price_watch.store.scrape._process_preload(mock_config, mock_driver, mock_wait, item, 0)

        mock_driver.get.assert_called_once_with("https://example.com/preload")

    def test_skip_by_every(self):
        """every 設定でスキップ"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = {
            "name": "Test",
            "preload": {
                "url": "https://example.com/preload",
                "every": 3,
                "action": [],
            },
        }

        # loop=1 は 3 で割り切れないのでスキップ
        price_watch.store.scrape._process_preload(mock_config, mock_driver, mock_wait, item, 1)

        mock_driver.get.assert_not_called()

    def test_run_on_every(self):
        """every に合致する場合は実行"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_wait = MagicMock()
        item = {
            "name": "Test",
            "preload": {
                "url": "https://example.com/preload",
                "every": 3,
                "action": [],
            },
        }

        # loop=3 は 3 で割り切れるので実行
        price_watch.store.scrape._process_preload(mock_config, mock_driver, mock_wait, item, 3)

        mock_driver.get.assert_called_once()


class TestCheckImpl:
    """_check_impl 関数のテスト"""

    def test_price_element_not_found(self):
        """価格要素が見つからない場合"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"
        item = {
            "name": "Test",
            "url": "https://example.com/item",
            "price_xpath": "//price",
        }

        with (
            patch("my_lib.selenium_util.xpath_exists", return_value=False),
            patch("my_lib.selenium_util.dump_page"),
        ):
            result = price_watch.store.scrape._check_impl(mock_config, mock_driver, item, 0)

        assert result["crawl_success"] is False
        assert "price" not in result

    def test_price_found_with_stock(self):
        """価格取得成功・在庫あり"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"

        mock_price_elem = MagicMock()
        mock_price_elem.text = "1,234円"
        mock_driver.find_element.return_value = mock_price_elem
        mock_driver.find_elements.return_value = []  # unavailable なし

        item = {
            "name": "Test",
            "url": "https://example.com/item",
            "price_xpath": "//price",
            "unavailable_xpath": "//unavailable",
        }

        with patch("my_lib.selenium_util.xpath_exists", return_value=True):
            result = price_watch.store.scrape._check_impl(mock_config, mock_driver, item, 0)

        assert result["crawl_success"] is True
        assert result["price"] == 1234
        assert result["stock"] == 1

    def test_price_found_without_stock(self):
        """価格取得成功・在庫なし"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"

        mock_price_elem = MagicMock()
        mock_price_elem.text = "在庫切れ"
        mock_driver.find_element.return_value = mock_price_elem
        # unavailable_xpath がマッチ
        mock_driver.find_elements.return_value = [MagicMock()]

        item = {
            "name": "Test",
            "url": "https://example.com/item",
            "price_xpath": "//price",
            "unavailable_xpath": "//unavailable",
        }

        with patch("my_lib.selenium_util.xpath_exists", return_value=True):
            result = price_watch.store.scrape._check_impl(mock_config, mock_driver, item, 0)

        assert result["crawl_success"] is True
        assert "price" not in result  # 在庫なしなので価格は設定されない
        assert result["stock"] == 0

    def test_no_unavailable_xpath_assumes_in_stock(self):
        """unavailable_xpath がない場合は在庫ありと仮定"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"

        mock_price_elem = MagicMock()
        mock_price_elem.text = "5,000円"
        mock_driver.find_element.return_value = mock_price_elem

        item = {
            "name": "Test",
            "url": "https://example.com/item",
            "price_xpath": "//price",
        }

        with patch("my_lib.selenium_util.xpath_exists", return_value=True):
            result = price_watch.store.scrape._check_impl(mock_config, mock_driver, item, 0)

        assert result["crawl_success"] is True
        assert result["price"] == 5000
        assert result["stock"] == 1

    def test_with_action(self):
        """アクションありの場合"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"

        mock_price_elem = MagicMock()
        mock_price_elem.text = "1,000円"
        mock_driver.find_element.return_value = mock_price_elem

        item = {
            "name": "Test",
            "url": "https://example.com/item",
            "price_xpath": "//price",
            "action": [{"type": "click", "xpath": "//button"}],
        }

        with (
            patch("my_lib.selenium_util.xpath_exists", return_value=True),
            patch("price_watch.store.scrape._process_action") as mock_action,
        ):
            result = price_watch.store.scrape._check_impl(mock_config, mock_driver, item, 0)

        mock_action.assert_called_once()
        assert result["price"] == 1000

    def test_thumbnail_from_img_xpath(self):
        """サムネイル画像の取得（img xpath）"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"

        mock_price_elem = MagicMock()
        mock_price_elem.text = "1,000円"

        mock_thumb_elem = MagicMock()
        mock_thumb_elem.get_attribute.return_value = "/images/thumb.jpg"

        def find_element(_by, xpath):
            if "price" in xpath:
                return mock_price_elem
            return mock_thumb_elem

        mock_driver.find_element.side_effect = find_element

        item = {
            "name": "Test",
            "url": "https://example.com/item",
            "price_xpath": "//price",
            "thumb_img_xpath": "//img/@src",
        }

        with (
            patch("my_lib.selenium_util.xpath_exists", return_value=True),
            patch("price_watch.thumbnail.save_thumb", return_value="/local/thumb.jpg"),
        ):
            result = price_watch.store.scrape._check_impl(mock_config, mock_driver, item, 0)

        assert result["thumb_url"] == "/local/thumb.jpg"

    def test_thumbnail_from_block_xpath(self):
        """サムネイル画像の取得（block xpath）"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"

        mock_price_elem = MagicMock()
        mock_price_elem.text = "1,000円"

        mock_block_elem = MagicMock()
        mock_block_elem.get_attribute.return_value = "background-image: url('images/thumb.jpg')"

        def find_element(_by, xpath):
            if "price" in xpath:
                return mock_price_elem
            return mock_block_elem

        mock_driver.find_element.side_effect = find_element

        item = {
            "name": "Test",
            "url": "https://example.com/item",
            "price_xpath": "//price",
            "thumb_url": "existing",  # これがあると thumb_block_xpath を使う
            "thumb_block_xpath": "//div[@class='thumb']",
        }

        with (
            patch("my_lib.selenium_util.xpath_exists", return_value=True),
            patch("price_watch.thumbnail.save_thumb", return_value="/local/thumb.jpg"),
        ):
            result = price_watch.store.scrape._check_impl(mock_config, mock_driver, item, 0)

        assert result["thumb_url"] == "/local/thumb.jpg"

    def test_price_parse_error_with_stock(self):
        """価格パースエラー（在庫あり）の場合は例外"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com/item"

        mock_price_elem = MagicMock()
        mock_price_elem.text = "価格未定"
        mock_driver.find_element.return_value = mock_price_elem
        mock_driver.find_elements.return_value = []  # unavailable なし

        item = {
            "name": "Test",
            "url": "https://example.com/item",
            "price_xpath": "//price",
            "unavailable_xpath": "//unavailable",
        }

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
        item = {"name": "Test", "url": "https://example.com/item", "price_xpath": "//price"}

        with patch("price_watch.store.scrape._check_impl") as mock_impl:
            mock_impl.return_value = item

            with patch("my_lib.selenium_util.error_handler") as mock_handler:
                # コンテキストマネージャーをモック
                mock_handler.return_value.__enter__ = MagicMock(return_value=None)
                mock_handler.return_value.__exit__ = MagicMock(return_value=False)

                result = price_watch.store.scrape.check(mock_config, mock_driver, item, 0)

        assert result == item

    def test_error_handler_calls_notify_on_error(self):
        """エラー発生時に notify.error_with_page が呼ばれる"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        mock_driver.current_url = "https://example.com"
        item = {"name": "Test", "url": "https://example.com/item", "price_xpath": "//price"}

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
            mock_impl.return_value = item
            price_watch.store.scrape.check(mock_config, mock_driver, item, 0)

            # on_error コールバックを実行
            if captured_on_error:
                test_exc = Exception("Test error")
                captured_on_error(test_exc, None, None)

        mock_notify.assert_called_once()
