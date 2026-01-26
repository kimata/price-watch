#!/usr/bin/env python3
"""Amazon PA-API を使った価格チェック."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import my_lib.store.amazon.api
import my_lib.store.amazon.config

import price_watch.models
import price_watch.store.amazon.paapi_rate_limiter
import price_watch.thumbnail

if TYPE_CHECKING:
    from price_watch.config import AppConfig
    from price_watch.target import ResolvedItem


def check_item_list(config: AppConfig, item_list: list[ResolvedItem]) -> list[price_watch.models.CheckedItem]:
    """アイテムリストの価格をチェック.

    Args:
        config: アプリケーション設定
        item_list: チェック対象アイテムのリスト

    Returns:
        チェック結果のリスト
    """
    if not item_list:
        return []

    if config.store.amazon_api is None:
        logging.warning("Amazon API config is not set")
        return []

    try:
        api_config = config.store.amazon_api

        # ResolvedItem を AmazonItem に変換
        amazon_items = [
            my_lib.store.amazon.config.AmazonItem(asin=item.asin or "", url=item.url) for item in item_list
        ]

        # レートリミッターで API 呼び出し間隔を制御（1 TPS）
        with price_watch.store.amazon.paapi_rate_limiter.get_rate_limiter(tps=1.0):
            # PA-API で価格チェック
            result_items = my_lib.store.amazon.api.check_item_list(api_config, amazon_items)

        # 結果を元の item_list に反映
        result_map = {item.asin: item for item in result_items}

        checked_items: list[price_watch.models.CheckedItem] = []
        for item in item_list:
            result = price_watch.models.CheckedItem.from_resolved_item(item)
            result.crawl_status = price_watch.models.CrawlStatus.SUCCESS

            if item.asin and item.asin in result_map:
                api_result = result_map[item.asin]
                # 価格がある場合のみ在庫ありとする
                if api_result.price is not None:
                    result.stock = price_watch.models.StockStatus.IN_STOCK
                    result.price = api_result.price
                else:
                    result.stock = price_watch.models.StockStatus.OUT_OF_STOCK

                if api_result.thumb_url is not None:
                    # サムネイルをローカルに保存
                    local_url = price_watch.thumbnail.save_thumb(item.name, api_result.thumb_url)
                    result.thumb_url = local_url if local_url else api_result.thumb_url
            else:
                result.stock = price_watch.models.StockStatus.OUT_OF_STOCK

            checked_items.append(result)

        return checked_items
    except Exception:
        logging.exception("PA-API での価格取得に失敗しました")
        return []
