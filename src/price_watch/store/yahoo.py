#!/usr/bin/env python3
"""Yahoo!ショッピング検索による価格チェック."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import my_lib.store.yahoo.api

import price_watch.history
import price_watch.models

if TYPE_CHECKING:
    from price_watch.config import AppConfig
    from price_watch.target import ResolvedItem

# 検索結果の最大取得件数
MAX_SEARCH_RESULTS = 10


def _parse_cond(cond_str: str | None) -> my_lib.store.yahoo.api.Condition:
    """商品状態文字列をパース.

    Args:
        cond_str: 商品状態文字列（"new" or "used"）

    Returns:
        Condition enum
    """
    if not cond_str:
        return my_lib.store.yahoo.api.Condition.NEW

    cond_map = {
        "new": my_lib.store.yahoo.api.Condition.NEW,
        "used": my_lib.store.yahoo.api.Condition.USED,
    }

    cond_lower = cond_str.strip().lower()
    if cond_lower in cond_map:
        return cond_map[cond_lower]

    logging.warning("Unknown Yahoo condition: %s, using NEW", cond_str)
    return my_lib.store.yahoo.api.Condition.NEW


def _build_search_condition(item: ResolvedItem) -> my_lib.store.yahoo.api.SearchCondition:
    """アイテム情報から検索条件を構築.

    Args:
        item: 監視対象アイテム

    Returns:
        SearchCondition
    """
    # キーワード: search_keyword がなければ name を使用
    keyword = item.search_keyword or item.name

    # 価格範囲
    price_min = None
    price_max = None
    if item.price_range:
        if len(item.price_range) >= 1:
            price_min = item.price_range[0]
        if len(item.price_range) >= 2:
            price_max = item.price_range[1]

    # 商品状態
    condition = _parse_cond(item.cond)

    return my_lib.store.yahoo.api.SearchCondition(
        keyword=keyword,
        jan=item.jan_code,
        price_min=price_min,
        price_max=price_max,
        condition=condition,
    )


def _build_search_cond_json(condition: my_lib.store.yahoo.api.SearchCondition) -> str:
    """検索条件を JSON 文字列に変換（item_key 生成用）.

    Args:
        condition: 検索条件

    Returns:
        JSON 文字列
    """
    data: dict[str, Any] = {}

    if condition.jan:
        data["jan"] = condition.jan
    if condition.price_min is not None:
        data["price_min"] = condition.price_min
    if condition.price_max is not None:
        data["price_max"] = condition.price_max
    if condition.condition != my_lib.store.yahoo.api.Condition.NEW:
        data["cond"] = condition.condition.value

    return json.dumps(data, sort_keys=True, ensure_ascii=False) if data else ""


def check(
    config: AppConfig,
    item: ResolvedItem,
) -> price_watch.models.CheckedItem:
    """Yahoo!ショッピング検索で最安値商品を取得.

    Args:
        config: アプリケーション設定
        item: 監視対象アイテム

    Returns:
        チェック結果（CheckedItem）
    """
    # 結果を格納する CheckedItem を作成
    result = price_watch.models.CheckedItem.from_resolved_item(item)

    # Yahoo API 設定がない場合はエラー
    if config.store.yahoo_api is None:
        logging.error("[Yahoo検索] Yahoo API 設定がありません")
        result.crawl_status = price_watch.models.CrawlStatus.FAILURE
        return result

    # 検索条件を構築
    condition = _build_search_condition(item)

    logging.info("[Yahoo検索] %s: キーワード='%s'", item.name, condition.keyword)
    if condition.jan:
        logging.info("[Yahoo検索] %s: JAN='%s'", item.name, condition.jan)

    # item_key 生成用のデータを設定
    # jan_code が指定されている場合は jan_code を使用、それ以外は search_keyword
    if item.jan_code:
        result.search_keyword = item.jan_code
    else:
        result.search_keyword = condition.keyword
    result.search_cond = _build_search_cond_json(condition)

    # 検索実行
    try:
        results = my_lib.store.yahoo.api.search(
            config.store.yahoo_api,
            condition,
            max_items=MAX_SEARCH_RESULTS,
        )
    except Exception:
        logging.exception("[Yahoo検索] %s: API エラー", item.name)
        result.crawl_status = price_watch.models.CrawlStatus.FAILURE
        return result

    if not results:
        logging.info("[Yahoo検索] %s: 検索結果なし", item.name)
        result.stock = price_watch.models.StockStatus.OUT_OF_STOCK
        result.crawl_status = price_watch.models.CrawlStatus.SUCCESS
        return result

    # 最安値を探す（API は価格の安い順でソートされているので先頭が最安値）
    cheapest = results[0]

    logging.info(
        "[Yahoo検索] %s: %d件中最安値 ¥%s - %s",
        item.name,
        len(results),
        f"{cheapest.price:,}",
        cheapest.name,
    )

    # 結果を設定
    result.url = cheapest.url
    result.price = cheapest.price
    result.thumb_url = cheapest.thumb_url
    result.stock = price_watch.models.StockStatus.IN_STOCK
    result.crawl_status = price_watch.models.CrawlStatus.SUCCESS

    return result


def generate_item_key(item: price_watch.models.CheckedItem) -> str:
    """Yahoo アイテム用の item_key を生成.

    Args:
        item: チェック済みアイテム

    Returns:
        item_key
    """
    return price_watch.history.generate_item_key(
        search_keyword=item.search_keyword,
        search_cond=item.search_cond,
        store_name=item.store,
    )
