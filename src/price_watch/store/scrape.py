#!/usr/bin/env python3
# ruff: noqa: S311
"""スクレイピングによる価格チェック."""

from __future__ import annotations

import logging
import random
import re
import string
import time
import urllib.parse
from typing import TYPE_CHECKING

import my_lib.selenium_util
import PIL.Image
import selenium.webdriver.common.by
import selenium.webdriver.support.wait

import price_watch.captcha
import price_watch.const
import price_watch.models
import price_watch.notify
import price_watch.thumbnail

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.support.wait import WebDriverWait as WebDriverWaitType

    from price_watch.config import AppConfig
    from price_watch.target import ResolvedItem

TIMEOUT_SEC = 4


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
    driver: WebDriver,
    wait: selenium.webdriver.support.wait.WebDriverWait,
    item: ResolvedItem,
    name: str = "action",
) -> None:
    """アクションを処理."""
    By = selenium.webdriver.common.by.By

    logging.info("process action: %s", item.name)

    for action in item.actions:
        action_type = action.type.value
        logging.debug("action: %s.", action_type)

        match action_type:
            case "input":
                if action.xpath is None:
                    continue
                xpath = _resolve_template(action.xpath, item)
                if not my_lib.selenium_util.xpath_exists(driver, xpath):
                    logging.debug("Element not found. Interrupted.")
                    return
                driver.find_element(By.XPATH, xpath).send_keys(_resolve_template(action.value or "", item))

            case "click":
                if action.xpath is None:
                    continue
                xpath = _resolve_template(action.xpath, item)
                if not my_lib.selenium_util.xpath_exists(driver, xpath):
                    logging.debug("Element not found. Interrupted.")
                    return
                driver.find_element(By.XPATH, xpath).click()

            case "recaptcha":
                price_watch.captcha.resolve_mp3(driver, wait)

            case "captcha":
                input_xpath = '//input[@id="captchacharacters"]'
                if not my_lib.selenium_util.xpath_exists(driver, input_xpath):
                    logging.debug("Element not found.")
                    continue
                domain = urllib.parse.urlparse(driver.current_url).netloc

                logging.warning("Resolve captcha is needed at %s.", domain)

                my_lib.selenium_util.dump_page(
                    driver, int(random.random() * 100), price_watch.const.DUMP_PATH
                )
                code = input(f"{domain} captcha: ")

                driver.find_element(By.XPATH, input_xpath).send_keys(code)
                driver.find_element(By.XPATH, '//button[@type="submit"]').click()

            case "sixdigit":
                digit_code = input(f"{urllib.parse.urlparse(driver.current_url).netloc} app code: ")
                for i, code in enumerate(list(digit_code)):
                    driver.find_element(By.XPATH, f'//input[@data-id="{i}"]').send_keys(code)

        time.sleep(4)


def _process_preload(
    config: AppConfig,
    driver: WebDriver,
    wait: selenium.webdriver.support.wait.WebDriverWait,
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

    driver.get(item.preload.url)
    time.sleep(2)

    # プリロード用のアクションがあれば実行
    # NOTE: 現状 preload にはアクションがないのでスキップ


def _check_impl(
    config: AppConfig,
    driver: WebDriver,
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
    By = selenium.webdriver.common.by.By
    WebDriverWait = selenium.webdriver.support.wait.WebDriverWait

    wait: WebDriverWaitType = WebDriverWait(driver, TIMEOUT_SEC)
    _process_preload(config, driver, wait, item, loop)

    logging.info("fetch: %s", item.url)

    driver.get(item.url)
    time.sleep(2)

    if item.actions:
        _process_action(config, driver, wait, item)

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

    price_xpath_exists = my_lib.selenium_util.xpath_exists(driver, item.price_xpath)

    if not price_xpath_exists:
        # 価格要素が見つからない → クロール失敗
        logging.warning("%s: price element not found (crawl failure).", item.name)
        my_lib.selenium_util.dump_page(driver, int(random.random() * 100), price_watch.const.DUMP_PATH)
        result.crawl_status = price_watch.models.CrawlStatus.FAILURE
    else:
        # 価格要素が見つかった → 在庫状態を確認
        if item.unavailable_xpath is not None:
            # unavailable_xpath が定義されている場合、在庫状態を判定可能
            stock_found = True
            if driver.find_elements(By.XPATH, item.unavailable_xpath):
                result.stock = price_watch.models.StockStatus.OUT_OF_STOCK
            else:
                result.stock = price_watch.models.StockStatus.IN_STOCK
        else:
            # unavailable_xpath がない場合、価格要素があれば在庫ありと仮定
            stock_found = True
            result.stock = price_watch.models.StockStatus.IN_STOCK

        # 価格を取得（複数要素がマッチする場合、表示されているものを優先）
        price_elements = driver.find_elements(By.XPATH, item.price_xpath)
        price_element = next(
            (e for e in price_elements if e.is_displayed()),
            price_elements[0] if price_elements else None,
        )
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
        if my_lib.selenium_util.xpath_exists(driver, elem_xpath):
            thumb_url = urllib.parse.urljoin(
                driver.current_url,
                driver.find_element(By.XPATH, elem_xpath).get_attribute(attr_name),
            )

    # サムネイルをローカルに保存
    if thumb_url:
        local_url = price_watch.thumbnail.save_thumb(item.name, thumb_url)
        result.thumb_url = local_url if local_url else thumb_url

    return result


def check(
    config: AppConfig,
    driver: WebDriver,
    item: ResolvedItem,
    loop: int,
) -> price_watch.models.CheckedItem:
    """価格をチェック.

    エラー発生時は自動的にスクリーンショットとページソースを取得し、
    Slack にエラー通知を送信します。

    Args:
        config: アプリケーション設定
        driver: WebDriver インスタンス
        item: 監視対象アイテム
        loop: ループカウンタ

    Returns:
        チェック結果
    """
    # エラー時の通知用に CheckedItem を作成
    error_item = price_watch.models.CheckedItem.from_resolved_item(item)

    def on_error(
        exc: Exception,
        screenshot: PIL.Image.Image | None,
        page_source: str | None,
    ) -> None:
        """エラー発生時のコールバック."""
        logging.error("URL: %s", driver.current_url)
        price_watch.notify.error_with_page(
            config.slack,
            error_item,
            exc,
            screenshot,
            page_source,
        )

    logging.info("Check %s", item.name)

    with my_lib.selenium_util.error_handler(
        driver,
        message=f"Failed to check price: {item.name}",
        on_error=on_error,
        reraise=True,
    ):
        return _check_impl(config, driver, item, loop)

    # error_handler が reraise=True なので例外発生時はここに到達しない
    raise AssertionError("Unreachable: error_handler should have reraised exception")
