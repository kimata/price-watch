#!/usr/bin/env python3
"""スクレイピングによる価格チェック."""

from __future__ import annotations

import logging
import random
import re
import string
import time
import urllib.parse
from typing import TYPE_CHECKING, Any

import my_lib.selenium_util
import PIL.Image
import selenium.webdriver.common.by
import selenium.webdriver.support.wait

import price_watch.captcha
import price_watch.const
import price_watch.notify
import price_watch.thumbnail

if TYPE_CHECKING:
    from price_watch.config import AppConfig

TIMEOUT_SEC = 4


def _resolve_template(template: str, item: dict[str, Any]) -> str:
    """テンプレート文字列を解決."""
    tmpl = string.Template(template)
    return tmpl.safe_substitute(item_name=item["name"])


def _process_action(
    config: AppConfig,
    driver: my_lib.selenium_util.WebDriverType,
    wait: selenium.webdriver.support.wait.WebDriverWait,  # type: ignore[type-arg]
    item: dict[str, Any],
    action_list: list[dict[str, Any]],
    name: str = "action",
) -> None:
    """アクションを処理."""
    By = selenium.webdriver.common.by.By

    logging.info("process action: %s", item["name"])

    for action in action_list:
        action_type = action["type"]
        logging.debug("action: %s.", action_type)

        match action_type:
            case "input":
                xpath = _resolve_template(action["xpath"], item)
                if not my_lib.selenium_util.xpath_exists(driver, xpath):
                    logging.debug("Element not found. Interrupted.")
                    return
                driver.find_element(By.XPATH, xpath).send_keys(_resolve_template(action["value"], item))

            case "click":
                xpath = _resolve_template(action["xpath"], item)
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
    driver: my_lib.selenium_util.WebDriverType,
    wait: selenium.webdriver.support.wait.WebDriverWait,  # type: ignore[type-arg]
    item: dict[str, Any],
    loop: int,
) -> None:
    """プリロードを処理."""
    logging.info("process preload: %s", item["name"])

    if "preload" not in item:
        return

    if (loop % item["preload"]["every"]) != 0:
        logging.info("skip preload. (loop=%d)", loop)
        return

    driver.get(item["preload"]["url"])
    time.sleep(2)

    _process_action(config, driver, wait, item, item["preload"]["action"], "preload action")


def _check_impl(
    config: AppConfig,
    driver: my_lib.selenium_util.WebDriverType,
    item: dict[str, Any],
    loop: int,
) -> dict[str, Any] | bool:
    """価格チェック実装."""
    By = selenium.webdriver.common.by.By
    WebDriverWait = selenium.webdriver.support.wait.WebDriverWait

    wait: WebDriverWait = WebDriverWait(driver, TIMEOUT_SEC)  # type: ignore[type-arg]

    _process_preload(config, driver, wait, item, loop)

    logging.info("fetch: %s", item["url"])

    driver.get(item["url"])
    time.sleep(2)

    if "action" in item:
        _process_action(config, driver, wait, item, item["action"])

    logging.info("parse: %s", item["name"])

    # 価格要素の存在確認
    price_found = my_lib.selenium_util.xpath_exists(driver, item["price_xpath"])

    if not price_found:
        logging.warning("%s: price not found.", item["name"])
        item["stock"] = 0
        my_lib.selenium_util.dump_page(driver, int(random.random() * 100), price_watch.const.DUMP_PATH)
    else:
        # 在庫状態を確認
        if "unavailable_xpath" in item:
            if driver.find_elements(By.XPATH, item["unavailable_xpath"]):
                item["stock"] = 0
            else:
                item["stock"] = 1
        else:
            item["stock"] = 1

        # 価格を取得
        price_text = driver.find_element(By.XPATH, item["price_xpath"]).text
        try:
            m = re.match(r".*?(\d{1,3}(?:,\d{3})*)", price_text)
            if m is None:
                raise ValueError(f"Invalid price format: {price_text}")
            item["price"] = int(m.group(1).replace(",", ""))
        except Exception:
            if item["stock"] == 0:
                pass
            else:
                logging.debug("unable to parse price: '%s'", price_text)
                raise

    # サムネイル画像を取得（価格が取得できなくても実行）
    if "thumb_url" not in item:
        if ("thumb_img_xpath" in item) and my_lib.selenium_util.xpath_exists(driver, item["thumb_img_xpath"]):
            item["thumb_url"] = urllib.parse.urljoin(
                driver.current_url,
                driver.find_element(By.XPATH, item["thumb_img_xpath"]).get_attribute("src"),
            )
    elif ("thumb_block_xpath" in item) and my_lib.selenium_util.xpath_exists(
        driver, item["thumb_block_xpath"]
    ):
        style_text = driver.find_element(By.XPATH, item["thumb_block_xpath"]).get_attribute("style")
        m = re.match(r"background-image: url\([\"'](.*)[\"']\)", style_text)
        if m:
            thumb_url = m.group(1)
            if not re.compile(r"^\.\.").search(thumb_url):
                thumb_url = "/" + thumb_url
            item["thumb_url"] = urllib.parse.urljoin(driver.current_url, thumb_url)

    # サムネイルをローカルに保存
    if item.get("thumb_url"):
        local_url = price_watch.thumbnail.save_thumb(item["name"], item["thumb_url"])
        if local_url:
            item["thumb_url"] = local_url

    return item


def check(
    config: AppConfig,
    driver: my_lib.selenium_util.WebDriverType,
    item: dict[str, Any],
    loop: int,
) -> dict[str, Any] | bool:
    """価格をチェック.

    エラー発生時は自動的にスクリーンショットとページソースを取得し、
    Slack にエラー通知を送信します。
    """

    def on_error(
        exc: Exception,
        screenshot: PIL.Image.Image | None,
        page_source: str | None,
    ) -> None:
        """エラー発生時のコールバック."""
        logging.error("URL: %s", driver.current_url)
        price_watch.notify.error_with_page(
            config.slack,
            item,
            exc,
            screenshot,
            page_source,
        )

    logging.info("Check %s", item["name"])

    with my_lib.selenium_util.error_handler(
        driver,
        message=f"Failed to check price: {item['name']}",
        on_error=on_error,
        reraise=True,
    ):
        return _check_impl(config, driver, item, loop)

    # error_handler が reraise=True なので例外発生時はここに到達しない
    # 型チェックのためのフォールバック
    return False
