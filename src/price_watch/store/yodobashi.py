#!/usr/bin/env python3
"""ヨドバシ.com 専用スクレイピングによる価格チェック.

my_lib.store.yodobashi.scrape を使用して商品ページから価格情報を取得します。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import my_lib.store.yodobashi
import selenium.webdriver.support.wait

import price_watch.models

if TYPE_CHECKING:
    import selenium.webdriver.remote.webdriver

    from price_watch.config import AppConfig
    from price_watch.target import ResolvedItem


def check(
    config: AppConfig,
    driver: selenium.webdriver.remote.webdriver.WebDriver,
    item: ResolvedItem,
) -> price_watch.models.CheckedItem:
    """ヨドバシ商品ページから価格情報を取得.

    Args:
        config: アプリケーション設定（現在未使用だが将来の拡張用）
        driver: WebDriver インスタンス
        item: 監視対象アイテム

    Returns:
        チェック結果（CheckedItem）
    """
    # 結果を格納する CheckedItem を作成
    result = price_watch.models.CheckedItem.from_resolved_item(item)

    # WebDriverWait を作成（タイムアウト 10 秒）
    wait = selenium.webdriver.support.wait.WebDriverWait(driver, 10)

    logging.info("[ヨドバシ] %s: スクレイピング開始 - %s", item.name, item.url)

    try:
        # my_lib.store.yodobashi.scrape を呼び出し
        product_info = my_lib.store.yodobashi.scrape(driver, wait, item.url)

        # 結果を CheckedItem に変換
        if product_info.price is not None:
            result.price = product_info.price
            result.crawl_status = price_watch.models.CrawlStatus.SUCCESS
            logging.info("[ヨドバシ] %s: 価格取得成功 ¥%s", item.name, f"{product_info.price:,}")
        else:
            result.crawl_status = price_watch.models.CrawlStatus.FAILURE
            logging.warning("[ヨドバシ] %s: 価格取得失敗", item.name)

        # サムネイル URL
        if product_info.thumbnail_url:
            result.thumb_url = product_info.thumbnail_url

        # 在庫状態
        if product_info.in_stock:
            result.stock = price_watch.models.StockStatus.IN_STOCK
        else:
            result.stock = price_watch.models.StockStatus.OUT_OF_STOCK
            logging.info("[ヨドバシ] %s: 在庫なし", item.name)

    except Exception:
        logging.exception("[ヨドバシ] %s: スクレイピングエラー", item.name)
        result.crawl_status = price_watch.models.CrawlStatus.FAILURE

    return result
