#!/usr/bin/env python3
"""楽天市場検索による価格チェック."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import my_lib.store.rakuten.api

import price_watch.history
import price_watch.models
import price_watch.store.search_filter

if TYPE_CHECKING:
    from price_watch.config import AppConfig
    from price_watch.target import ResolvedItem

# 検索結果の最大取得件数
MAX_SEARCH_RESULTS = 10


def _build_search_condition(item: ResolvedItem) -> my_lib.store.rakuten.api.SearchCondition:
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

    # 除外キーワード
    ng_keyword = item.exclude_keyword

    return my_lib.store.rakuten.api.SearchCondition(
        keyword=keyword,
        ng_keyword=ng_keyword,
        price_min=price_min,
        price_max=price_max,
    )


def _build_search_cond_json(condition: my_lib.store.rakuten.api.SearchCondition) -> str:
    """検索条件を JSON 文字列に変換（item_key 生成用）.

    Args:
        condition: 検索条件

    Returns:
        JSON 文字列
    """
    data: dict[str, Any] = {}

    if condition.ng_keyword:
        data["ng_keyword"] = condition.ng_keyword
    if condition.price_min is not None:
        data["price_min"] = condition.price_min
    if condition.price_max is not None:
        data["price_max"] = condition.price_max

    return json.dumps(data, sort_keys=True, ensure_ascii=False) if data else ""


def check(
    config: AppConfig,
    item: ResolvedItem,
) -> price_watch.models.CheckedItem:
    """楽天市場検索で最安値商品を取得.

    Args:
        config: アプリケーション設定
        item: 監視対象アイテム

    Returns:
        チェック結果（CheckedItem）
    """
    # 結果を格納する CheckedItem を作成
    result = price_watch.models.CheckedItem.from_resolved_item(item)

    # 楽天 API 設定がない場合はエラー
    if config.store.rakuten_api is None:
        logging.error("[楽天検索] 楽天 API 設定がありません")
        result.crawl_status = price_watch.models.CrawlStatus.FAILURE
        return result

    # 検索条件を構築
    condition = _build_search_condition(item)

    logging.info("[楽天検索] %s: キーワード='%s'", item.name, condition.keyword)
    if condition.ng_keyword:
        logging.info("[楽天検索] %s: 除外キーワード='%s'", item.name, condition.ng_keyword)
    if item.affiliate_id:
        logging.debug("[楽天検索] %s: アフィリエイトID='%s'", item.name, item.affiliate_id)

    # item_key 生成用のデータを設定
    result.search_keyword = condition.keyword
    result.search_cond = _build_search_cond_json(condition)

    # 検索実行
    try:
        results = my_lib.store.rakuten.api.search(
            config.store.rakuten_api,
            condition,
            max_items=MAX_SEARCH_RESULTS,
            affiliate_id=item.affiliate_id,
        )
    except Exception:
        logging.exception("[楽天検索] %s: API エラー", item.name)
        result.crawl_status = price_watch.models.CrawlStatus.FAILURE
        return result

    if not results:
        logging.info("[楽天検索] %s: 検索結果なし", item.name)
        result.stock = price_watch.models.StockStatus.OUT_OF_STOCK
        result.crawl_status = price_watch.models.CrawlStatus.SUCCESS
        return result

    # キーワード全断片一致フィルタ
    before_keyword_filter = len(results)
    results = [
        r for r in results if price_watch.store.search_filter.matches_all_keywords(r.name, condition.keyword)
    ]
    if len(results) < before_keyword_filter:
        logging.info(
            "[楽天検索] %s: キーワード不一致の商品を除外 (%d件 -> %d件)",
            item.name,
            before_keyword_filter,
            len(results),
        )
    if not results:
        logging.info("[楽天検索] %s: キーワード一致する商品なし", item.name)
        result.stock = price_watch.models.StockStatus.OUT_OF_STOCK
        result.crawl_status = price_watch.models.CrawlStatus.SUCCESS
        return result

    # 最安値を探す（API は価格の安い順でソートされているので先頭が最安値）
    cheapest = results[0]

    logging.info(
        "[楽天検索] %s: %d件中最安値 ¥%s - %s",
        item.name,
        len(results),
        f"{cheapest.price:,}",
        cheapest.name,
    )

    # 結果を設定
    result.url = cheapest.url
    result.price = cheapest.price
    # NOTE: 楽天検索結果のサムネイルは使用しない（検索のたびに別商品になる可能性があるため）
    result.stock = price_watch.models.StockStatus.IN_STOCK
    result.crawl_status = price_watch.models.CrawlStatus.SUCCESS

    return result


def generate_item_key(item: price_watch.models.CheckedItem) -> str:
    """楽天アイテム用の item_key を生成.

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
