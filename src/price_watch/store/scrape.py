#!/usr/bin/env python3
# ruff: noqa: S311
"""スクレイピングによる価格チェック."""

from __future__ import annotations

import io
import logging
import random
import re
import string
import time
import urllib.parse
from typing import TYPE_CHECKING

import my_lib.browser
import my_lib.browser.helpers
import PIL.Image
from my_lib.browser import Xpath

import price_watch.captcha
import price_watch.const
import price_watch.models
import price_watch.notify
import price_watch.thumbnail
from price_watch.security.url_guard import validate_public_url

if TYPE_CHECKING:
    from my_lib.browser import Element, Page

    from price_watch.config import AppConfig
    from price_watch.target import ResolvedItem


def _parse_xpath_attr(xpath: str) -> tuple[str, str]:
    """XPath から要素パスと属性名を分離.

    ``//img/@src`` のように ``/@attr`` で終わる場合は要素部分と属性名を返す。
    属性指定がない場合はデフォルトで ``src`` を使用する。
    """
    match = re.match(r"^(.+?)/@(\w+)$", xpath)
    if match:
        return match.group(1), match.group(2)
    return xpath, "src"


def _resolve_template(template: str, item: ResolvedItem) -> str:
    """テンプレート文字列を解決."""
    tmpl = string.Template(template)
    return tmpl.safe_substitute(item_name=item.name)


def _process_action(
    config: AppConfig,
    page: Page,
    item: ResolvedItem,
    name: str = "action",
) -> None:
    """アクションを処理."""
    logging.info("process action: %s", item.name)

    for action in item.actions:
        action_type = action.type.value
        logging.debug("action: %s.", action_type)

        match action_type:
            case "input":
                if action.xpath is None:
                    continue
                xpath = _resolve_template(action.xpath, item)
                element = page.find(Xpath(xpath))
                if element is None:
                    logging.debug("Element not found. Interrupted.")
                    return
                element.type(_resolve_template(action.value or "", item))

            case "click":
                if action.xpath is None:
                    continue
                xpath = _resolve_template(action.xpath, item)
                element = page.find(Xpath(xpath))
                if element is None:
                    logging.debug("Element not found. Interrupted.")
                    return
                element.click()

            case "recaptcha":
                price_watch.captcha.resolve_mp3(page)

            case "captcha":
                input_xpath = '//input[@id="captchacharacters"]'
                input_elem = page.find(Xpath(input_xpath))
                if input_elem is None:
                    logging.debug("Element not found.")
                    continue
                domain = urllib.parse.urlparse(page.url).netloc

                logging.warning("Resolve captcha is needed at %s.", domain)

                my_lib.browser.helpers.dump_page(
                    page, int(random.random() * 100), price_watch.const.DUMP_PATH
                )
                code = input(f"{domain} captcha: ")

                input_elem.type(code)
                submit = page.find(Xpath('//button[@type="submit"]'))
                if submit is not None:
                    submit.click()

            case "sixdigit":
                digit_code = input(f"{urllib.parse.urlparse(page.url).netloc} app code: ")
                for i, code in enumerate(list(digit_code)):
                    digit_elem = page.find(Xpath(f'//input[@data-id="{i}"]'))
                    if digit_elem is not None:
                        digit_elem.type(code)

        time.sleep(4)


def _process_preload(
    config: AppConfig,
    page: Page,
    item: ResolvedItem,
    loop: int,
) -> None:
    """プリロードを処理."""
    logging.info("process preload: %s", item.name)

    if item.preload is None:
        return

    if (loop % item.preload.every) != 0:
        logging.info("skip preload. (loop=%d)", loop)
        return

    validate_public_url(item.preload.url)
    page.goto(item.preload.url)
    time.sleep(2)

    # プリロード用のアクションがあれば実行
    # NOTE: 現状 preload にはアクションがないのでスキップ


def _select_visible_element(elements: list[Element]) -> Element | None:
    """表示されている要素を優先して 1 つ選択."""
    if not elements:
        return None
    for element in elements:
        if element.is_visible():
            return element
    return elements[0]


def _check_impl(
    config: AppConfig,
    page: Page,
    item: ResolvedItem,
    loop: int,
) -> price_watch.models.CheckedItem:
    """価格チェック実装.

    価格の扱いロジック:
    | 価格取得成否 | 在庫取得成否 | 在庫有無 | 価格の扱い |
    |-------------|-------------|---------|-----------|
    | False       | *           | *       | None      |
    | True        | False       | *       | None      |
    | True        | True        | False   | None      |
    | True        | True        | True    | 有効な価格 |
    """
    _process_preload(config, page, item, loop)

    logging.info("fetch: %s", item.url)

    validate_public_url(item.url)
    page.goto(item.url)
    time.sleep(2)

    if item.actions:
        _process_action(config, page, item)

    logging.info("parse: %s", item.name)

    # 結果を格納する CheckedItem を作成
    result = price_watch.models.CheckedItem.from_resolved_item(item)

    # 状態を初期化
    price_found = False
    stock_found = False
    parsed_price: int | None = None

    # 価格要素の存在確認
    if item.price_xpath is None:
        logging.warning("%s: price_xpath not configured.", item.name)
        result.crawl_status = price_watch.models.CrawlStatus.FAILURE
        return result

    price_xpath_exists = page.exists(Xpath(item.price_xpath), visible=False)

    if not price_xpath_exists:
        # 価格要素が見つからない場合でも、unavailable_xpath をチェック
        if item.unavailable_xpath is not None and page.find_all(Xpath(item.unavailable_xpath)):
            # 在庫なし状態（販売終了など）として SUCCESS 扱い
            result.stock = price_watch.models.StockStatus.OUT_OF_STOCK
            result.crawl_status = price_watch.models.CrawlStatus.SUCCESS
            logging.info("%s: price element not found, but unavailable detected (out of stock).", item.name)
        else:
            # unavailable_xpath が未定義またはマッチしない場合は FAILURE
            logging.warning("%s: price element not found (crawl failure).", item.name)
            my_lib.browser.helpers.dump_page(page, int(random.random() * 100), price_watch.const.DUMP_PATH)
            result.crawl_status = price_watch.models.CrawlStatus.FAILURE
    else:
        # 価格要素が見つかった → 在庫状態を確認
        if item.unavailable_xpath is not None:
            # unavailable_xpath が定義されている場合、在庫状態を判定可能
            stock_found = True
            if page.find_all(Xpath(item.unavailable_xpath)):
                result.stock = price_watch.models.StockStatus.OUT_OF_STOCK
            else:
                result.stock = price_watch.models.StockStatus.IN_STOCK
        else:
            # unavailable_xpath がない場合、価格要素があれば在庫ありと仮定
            stock_found = True
            result.stock = price_watch.models.StockStatus.IN_STOCK

        # 価格を取得（複数要素がマッチする場合、表示されているものを優先）
        price_elements = list(page.find_all(Xpath(item.price_xpath)))
        price_element = _select_visible_element(price_elements)
        price_text = price_element.text if price_element else ""
        try:
            m = re.match(r".*?(\d{1,3}(?:,\d{3})*)", price_text)
            if m is None:
                raise ValueError(f"Invalid price format: {price_text}")
            parsed_price = int(m.group(1).replace(",", ""))
            price_found = True
        except Exception:
            if result.stock == price_watch.models.StockStatus.OUT_OF_STOCK:
                # 在庫なしの場合、価格パース失敗は許容
                price_found = False
            else:
                # 在庫ありで価格パース失敗はエラー
                logging.debug("unable to parse price: '%s'", price_text)
                raise

        # 価格の設定ロジック:
        # 価格取得成功 AND 在庫取得成功 AND 在庫あり の場合のみ有効な価格を設定
        if price_found and stock_found and result.stock == price_watch.models.StockStatus.IN_STOCK:
            result.price = parsed_price
        # それ以外は price を設定しない（None 扱い）

        result.crawl_status = price_watch.models.CrawlStatus.SUCCESS

    # サムネイル画像を取得（価格が取得できなくても実行）
    thumb_url: str | None = None
    if item.thumb_img_xpath is not None:
        elem_xpath, attr_name = _parse_xpath_attr(item.thumb_img_xpath)
        thumb_elem = page.find(Xpath(elem_xpath))
        if thumb_elem is not None:
            thumb_url = urllib.parse.urljoin(
                page.url,
                thumb_elem.attr(attr_name),
            )

    # サムネイルをローカルに保存
    if thumb_url:
        local_url = price_watch.thumbnail.save_thumb(item.name, thumb_url)
        result.thumb_url = local_url if local_url else thumb_url

    return result


def check(
    config: AppConfig,
    page: Page,
    item: ResolvedItem,
    loop: int,
) -> price_watch.models.CheckedItem:
    """価格をチェック.

    エラー発生時は自動的にスクリーンショットとページソースを取得し、
    Slack にエラー通知を送信します。

    Args:
        config: アプリケーション設定
        page: ブラウザページ
        item: 監視対象アイテム
        loop: ループカウンタ

    Returns:
        チェック結果
    """
    logging.info("Check %s", item.name)

    try:
        return _check_impl(config, page, item, loop)
    except Exception as exc:
        logging.exception("Failed to check price: %s", item.name)

        # エラー時の通知用に CheckedItem を作成
        error_item = price_watch.models.CheckedItem.from_resolved_item(item)

        # スクリーンショット・ページソースを取得
        screenshot: PIL.Image.Image | None = None
        page_source: str | None = None
        try:
            page_source = page.content
        except Exception:
            logging.debug("Failed to capture page source for error handling")
        try:
            screenshot = PIL.Image.open(io.BytesIO(page.screenshot()))
        except Exception:
            logging.debug("Failed to capture screenshot for error handling")

        try:
            logging.error("URL: %s", page.url)
        except Exception:
            logging.debug("Failed to get current URL for error handling")

        price_watch.notify.error_with_page(
            config.slack,
            error_item,
            exc,
            screenshot,
            page_source,
        )
        raise
