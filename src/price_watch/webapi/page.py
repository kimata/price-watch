#!/usr/bin/env python3
"""API エンドポイント."""

from __future__ import annotations

import logging

import flask

from price_watch import history, thumbnail
from price_watch import item as item_module
from price_watch import target as target_module

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
        return item_module.get_target_urls()
    except Exception:
        logging.warning("Failed to load target.yaml, showing all items")
        return set()


def _get_target_config() -> target_module.TargetConfig | None:
    """target.yaml の設定を取得."""
    try:
        return target_module.load()
    except Exception:
        logging.warning("Failed to load target.yaml config")
        return None


def _get_point_rate(target_config: target_module.TargetConfig | None, store_name: str) -> float:
    """ストアのポイント還元率を取得."""
    if target_config is None:
        return 0.0
    store = target_config.get_store(store_name)
    return store.point_rate if store else 0.0


def _calc_effective_price(price: int, point_rate: float) -> int:
    """実質価格を計算（ポイント還元考慮）."""
    return int(price * (1 - point_rate / 100))


@blueprint.route("/api/items")
def get_items() -> flask.Response:
    """アイテム一覧を取得（複数ストア対応・実質価格付き）."""
    try:
        days_str = flask.request.args.get("days", "30")
        days = _parse_days(days_str)

        # target.yaml の設定を取得
        target_config = _get_target_config()
        target_urls = _get_target_urls()

        all_items = history.get_all_items()

        # アイテム名でグルーピング
        items_by_name: dict[str, list[dict]] = {}

        for item in all_items:
            # target.yaml に含まれないアイテムはスキップ
            if target_urls and item["url"] not in target_urls:
                continue
            # 最新価格を取得
            latest = history.get_latest_price(item["id"])
            if not latest:
                continue

            # 統計情報を取得
            stats = history.get_item_stats(item["id"], days)

            # 価格履歴を取得
            _, hist = history.get_item_history(item["url_hash"], days)

            # ポイント還元率を取得
            point_rate = _get_point_rate(target_config, item["store"])
            current_price = latest["price"]
            effective_price = _calc_effective_price(current_price, point_rate)

            formatted_history = [
                {
                    "time": h["time"],
                    "price": h["price"],
                    "effective_price": _calc_effective_price(h["price"], point_rate),
                    "stock": h["stock"],
                }
                for h in hist
            ]

            store_entry = {
                "url_hash": item["url_hash"],
                "store": item["store"],
                "url": item["url"],
                "current_price": current_price,
                "effective_price": effective_price,
                "point_rate": point_rate,
                "lowest_price": stats["lowest_price"],
                "highest_price": stats["highest_price"],
                "stock": latest["stock"],
                "last_updated": latest["time"],
                "history": formatted_history,
            }

            item_name = item["name"]
            if item_name not in items_by_name:
                items_by_name[item_name] = []
            items_by_name[item_name].append(
                {
                    "store_entry": store_entry,
                    "thumb_url": item["thumb_url"],
                }
            )

        # グルーピングされたアイテムを構築
        result_items = []
        for name, store_data_list in items_by_name.items():
            stores = [sd["store_entry"] for sd in store_data_list]

            # 最安ストアを決定（在庫ありの中で effective_price が最小）
            in_stock_stores = [s for s in stores if s["stock"] > 0]
            if in_stock_stores:
                best_store_entry = min(in_stock_stores, key=lambda s: s["effective_price"])
            else:
                # 在庫なしの場合も effective_price 最小を選択
                best_store_entry = min(stores, key=lambda s: s["effective_price"])

            # サムネイル URL（最初に取得されたものを使用）
            thumb_url = None
            for sd in store_data_list:
                if sd["thumb_url"]:
                    thumb_url = sd["thumb_url"]
                    break

            result_items.append(
                {
                    "name": name,
                    "thumb_url": thumb_url,
                    "stores": stores,
                    "best_store": best_store_entry["store"],
                    "best_effective_price": best_store_entry["effective_price"],
                }
            )

        # ストア定義を生成
        store_definitions = []
        if target_config:
            store_definitions = [
                {"name": store.name, "point_rate": store.point_rate}
                for store in target_config.stores
                if store.point_rate > 0
            ]

        return flask.jsonify(
            {
                "items": result_items,
                "store_definitions": store_definitions,
            }
        )

    except Exception:
        logging.exception("Error getting items")
        return flask.jsonify({"error": "Internal server error"}), 500  # type: ignore[return-value]


@blueprint.route("/thumb/<filename>")
def serve_thumb(filename: str) -> flask.Response:
    """サムネイル画像を配信."""
    # セキュリティチェック: ファイル名が正当な形式か確認
    if not filename.endswith(".png") or "/" in filename or "\\" in filename:
        return flask.Response("Not found", status=404)

    thumb_file = thumbnail.get_thumb_dir() / filename
    if not thumb_file.exists():
        return flask.Response("Not found", status=404)

    return flask.send_file(
        thumb_file,
        mimetype="image/png",
        max_age=86400,  # 24時間キャッシュ
    )


@blueprint.route("/api/items/<url_hash>/history")
def get_item_history(url_hash: str) -> flask.Response:
    """アイテム別価格履歴を取得."""
    try:
        days_str = flask.request.args.get("days", "30")
        days = _parse_days(days_str)

        item, hist = history.get_item_history(url_hash, days)

        if item is None:
            return flask.jsonify({"error": "Item not found"}), 404  # type: ignore[return-value]

        formatted_history = [
            {
                "time": h["time"],
                "price": h["price"],
                "stock": h["stock"],
            }
            for h in hist
        ]

        return flask.jsonify({"history": formatted_history})

    except Exception:
        logging.exception("Error getting item history")
        return flask.jsonify({"error": "Internal server error"}), 500  # type: ignore[return-value]
