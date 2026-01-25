#!/usr/bin/env python3
"""API エンドポイント."""

import logging
from typing import Any

import flask
from flask_pydantic import validate

import price_watch.history
import price_watch.item
import price_watch.target
import price_watch.thumbnail
import price_watch.webapi.schemas as schemas

blueprint = flask.Blueprint("page", __name__)


def _parse_days(days_str: str | None) -> int | None:
    """期間パラメータをパース."""
    if not days_str or days_str == "all":
        return None
    try:
        return int(days_str)
    except ValueError:
        return 30


def _get_target_urls() -> set[str]:
    """target.yaml から監視対象URLのセットを取得."""
    try:
        return price_watch.item.get_target_urls()
    except Exception:
        logging.warning("Failed to load target.yaml, showing all items")
        return set()


def _get_target_config() -> price_watch.target.TargetConfig | None:
    """target.yaml の設定を取得."""
    try:
        return price_watch.target.load()
    except Exception:
        logging.warning("Failed to load target.yaml config")
        return None


def _get_point_rate(target_config: price_watch.target.TargetConfig | None, store_name: str) -> float:
    """ストアのポイント還元率を取得."""
    if target_config is None:
        return 0.0
    store = target_config.get_store(store_name)
    return store.point_rate if store else 0.0


def _calc_effective_price(price: int, point_rate: float) -> int:
    """実質価格を計算（ポイント還元考慮）."""
    return int(price * (1 - point_rate / 100))


def _build_history_entries(history: list[dict[str, Any]], point_rate: float) -> list[schemas.HistoryEntry]:
    """履歴エントリリストを構築."""
    return [
        schemas.HistoryEntry(
            time=h["time"],
            price=h["price"],
            effective_price=_calc_effective_price(h["price"], point_rate),
            stock=h["stock"],
        )
        for h in history
    ]


def _build_store_entry(
    item: dict[str, Any],
    latest: dict[str, Any],
    stats: dict[str, Any],
    history: list[dict[str, Any]],
    point_rate: float,
) -> schemas.StoreEntry:
    """ストアエントリを構築."""
    current_price = latest["price"]
    effective_price = _calc_effective_price(current_price, point_rate)

    return schemas.StoreEntry(
        url_hash=item["url_hash"],
        store=item["store"],
        url=item["url"],
        current_price=current_price,
        effective_price=effective_price,
        point_rate=point_rate,
        lowest_price=stats["lowest_price"],
        highest_price=stats["highest_price"],
        stock=latest["stock"],
        last_updated=latest["time"],
        history=_build_history_entries(history, point_rate),
    )


def _find_best_store(stores: list[schemas.StoreEntry]) -> schemas.StoreEntry:
    """最安ストアを決定（在庫ありの中で effective_price が最小）."""
    in_stock_stores = [s for s in stores if s.stock > 0]
    if in_stock_stores:
        return min(in_stock_stores, key=lambda s: s.effective_price)
    # 在庫なしの場合も effective_price 最小を選択
    return min(stores, key=lambda s: s.effective_price)


def _find_first_thumb_url(store_data_list: list[dict[str, Any]]) -> str | None:
    """最初に見つかったサムネイルURLを取得."""
    for sd in store_data_list:
        if sd["thumb_url"]:
            return sd["thumb_url"]
    return None


def _build_result_item(name: str, store_data_list: list[dict[str, Any]]) -> schemas.ResultItem:
    """グルーピングされたアイテムから結果アイテムを構築."""
    stores = [sd["store_entry"] for sd in store_data_list]
    best_store_entry = _find_best_store(stores)
    thumb_url = _find_first_thumb_url(store_data_list)

    return schemas.ResultItem(
        name=name,
        thumb_url=thumb_url,
        stores=stores,
        best_store=best_store_entry.store,
        best_effective_price=best_store_entry.effective_price,
    )


def _get_store_definitions(
    target_config: price_watch.target.TargetConfig | None,
) -> list[schemas.StoreDefinition]:
    """ストア定義を生成."""
    if not target_config:
        return []
    return [
        schemas.StoreDefinition(name=store.name, point_rate=store.point_rate)
        for store in target_config.stores
    ]


def _process_item(
    item: dict[str, Any],
    days: int | None,
    target_config: price_watch.target.TargetConfig | None,
) -> dict[str, Any] | None:
    """1つのアイテムを処理してストアデータを構築."""
    # 最新価格を取得
    latest = price_watch.history.get_latest_price(item["id"])
    if not latest:
        return None

    # 統計情報を取得
    stats = price_watch.history.get_item_stats(item["id"], days)

    # 価格履歴を取得
    _, hist = price_watch.history.get_item_history(item["url_hash"], days)

    # ポイント還元率を取得
    point_rate = _get_point_rate(target_config, item["store"])

    store_entry = _build_store_entry(item, latest, stats, hist, point_rate)

    return {
        "store_entry": store_entry,
        "thumb_url": item["thumb_url"],
    }


def _group_items_by_name(
    all_items: list[dict[str, Any]],
    target_urls: set[str],
    days: int | None,
    target_config: price_watch.target.TargetConfig | None,
) -> dict[str, list[dict[str, Any]]]:
    """アイテムを名前でグルーピング."""
    items_by_name: dict[str, list[dict[str, Any]]] = {}

    for item in all_items:
        # target.yaml に含まれないアイテムはスキップ
        if target_urls and item["url"] not in target_urls:
            continue

        store_data = _process_item(item, days, target_config)
        if not store_data:
            continue

        item_name = item["name"]
        if item_name not in items_by_name:
            items_by_name[item_name] = []
        items_by_name[item_name].append(store_data)

    return items_by_name


@blueprint.route("/api/items")
@validate()
def get_items(query: schemas.ItemsQueryParams) -> flask.Response:
    """アイテム一覧を取得（複数ストア対応・実質価格付き）."""
    try:
        days = _parse_days(query.days)

        # target.yaml の設定を取得
        target_config = _get_target_config()
        target_urls = _get_target_urls()

        all_items = price_watch.history.get_all_items()

        # アイテム名でグルーピング
        items_by_name = _group_items_by_name(all_items, target_urls, days, target_config)

        # グルーピングされたアイテムを構築
        result_items = [
            _build_result_item(name, store_data_list) for name, store_data_list in items_by_name.items()
        ]

        response = schemas.ItemsResponse(
            items=result_items,
            store_definitions=_get_store_definitions(target_config),
        )

        return flask.jsonify(response.model_dump())

    except Exception:
        logging.exception("Error getting items")
        error = schemas.ErrorResponse(error="Internal server error")
        return flask.jsonify(error.model_dump()), 500


@blueprint.route("/thumb/<filename>")
def serve_thumb(filename: str) -> flask.Response:
    """サムネイル画像を配信."""
    # セキュリティチェック: ファイル名が正当な形式か確認
    if not filename.endswith(".png") or "/" in filename or "\\" in filename:
        return flask.Response("Not found", status=404)

    thumb_file = price_watch.thumbnail.get_thumb_dir() / filename
    if not thumb_file.exists():
        return flask.Response("Not found", status=404)

    return flask.send_file(
        thumb_file,
        mimetype="image/png",
        max_age=86400,  # 24時間キャッシュ
    )


@blueprint.route("/api/items/<url_hash>/history")
@validate()
def get_item_history(url_hash: str, query: schemas.ItemsQueryParams) -> flask.Response:
    """アイテム別価格履歴を取得."""
    try:
        days = _parse_days(query.days)

        item, hist = price_watch.history.get_item_history(url_hash, days)

        if item is None:
            error = schemas.ErrorResponse(error="Item not found")
            return flask.jsonify(error.model_dump()), 404

        formatted_history = [
            schemas.ItemHistoryEntry(
                time=h["time"],
                price=h["price"],
                stock=h["stock"],
            )
            for h in hist
        ]

        response = schemas.ItemHistoryResponse(history=formatted_history)
        return flask.jsonify(response.model_dump())

    except Exception:
        logging.exception("Error getting item history")
        error = schemas.ErrorResponse(error="Internal server error")
        return flask.jsonify(error.model_dump()), 500
