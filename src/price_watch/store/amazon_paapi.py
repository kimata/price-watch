#!/usr/bin/env python3
"""Amazon PA-API を使った価格チェック."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from my_lib.store.amazon.api import check_item_list as api_check_item_list
from my_lib.store.amazon.config import AmazonItem

from price_watch import thumbnail
from price_watch.store.paapi_rate_limiter import get_rate_limiter

if TYPE_CHECKING:
    from price_watch.config import AppConfig


def check_item_list(config: AppConfig, item_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """アイテムリストの価格をチェック.

    Args:
        config: アプリケーション設定
        item_list: チェック対象アイテムのリスト

    Returns:
        価格情報が更新されたアイテムリスト
    """
    if len(item_list) == 0:
        return []

    if config.store.amazon_api is None:
        logging.warning("Amazon API config is not set")
        return []

    try:
        api_config = config.store.amazon_api

        # dict を AmazonItem に変換
        amazon_items = [AmazonItem.parse(item) for item in item_list]

        # レートリミッターで API 呼び出し間隔を制御（1 TPS）
        with get_rate_limiter(tps=1.0):
            # PA-API で価格チェック
            result_items = api_check_item_list(api_config, amazon_items)

        # 結果を元の item_list に反映
        result_map = {item.asin: item for item in result_items}
        for item in item_list:
            if item["asin"] in result_map:
                result = result_map[item["asin"]]
                item["stock"] = result.stock if result.stock is not None else 0
                if result.price is not None:
                    item["price"] = result.price
                if result.thumb_url is not None:
                    # サムネイルをローカルに保存
                    local_url = thumbnail.save_thumb(item["name"], result.thumb_url)
                    item["thumb_url"] = local_url if local_url else result.thumb_url
            else:
                item["stock"] = 0

        return item_list
    except Exception:
        logging.exception("PA-API での価格取得に失敗しました")
        return []
