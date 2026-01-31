#!/usr/bin/env python3
"""Amazon 検索 API エンドポイント.

Amazon PA-API を使用したキーワード検索機能を提供します。
"""

import logging

import flask
import my_lib.store.amazon.api
from pydantic import BaseModel, Field

import price_watch.store.amazon.paapi_rate_limiter
import price_watch.webapi.cache

blueprint = flask.Blueprint("amazon_search", __name__)


class AmazonSearchRequest(BaseModel):
    """Amazon 検索リクエスト."""

    keywords: str = Field(..., min_length=1, max_length=200, description="検索キーワード")
    item_count: int = Field(default=10, ge=1, le=10, description="取得件数（1-10）")


class AmazonSearchResultItem(BaseModel):
    """Amazon 検索結果アイテム."""

    title: str
    asin: str
    price: int | None
    thumb_url: str | None


class AmazonSearchResponse(BaseModel):
    """Amazon 検索レスポンス."""

    items: list[AmazonSearchResultItem]


class ErrorResponse(BaseModel):
    """エラーレスポンス."""

    error: str


def _is_amazon_api_available() -> bool:
    """Amazon PA-API が利用可能かどうかを判定."""
    app_config = price_watch.webapi.cache.get_app_config()
    if app_config is None:
        return False
    return app_config.store.amazon_api is not None


@blueprint.route("/api/amazon/search/available", methods=["GET"])
def check_available() -> flask.Response:
    """Amazon 検索 API が利用可能かどうかを返す."""
    available = _is_amazon_api_available()
    return flask.jsonify({"available": available})


@blueprint.route("/api/amazon/search", methods=["POST"])
def search() -> flask.Response | tuple[flask.Response, int]:
    """Amazon 商品をキーワードで検索."""
    # リクエストのバリデーション
    try:
        data = flask.request.get_json()
        if data is None:
            error = ErrorResponse(error="リクエストボディが必要です")
            return flask.jsonify(error.model_dump()), 400

        request = AmazonSearchRequest.model_validate(data)
    except Exception as e:
        logging.warning("Amazon検索リクエストのバリデーションエラー: %s", e)
        error = ErrorResponse(error="リクエストの形式が正しくありません")
        return flask.jsonify(error.model_dump()), 400

    # Amazon PA-API 設定の確認
    app_config = price_watch.webapi.cache.get_app_config()
    if app_config is None:
        error = ErrorResponse(error="サーバー設定の読み込みに失敗しました")
        return flask.jsonify(error.model_dump()), 500

    amazon_api_config = app_config.store.amazon_api
    if amazon_api_config is None:
        error = ErrorResponse(error="Amazon PA-API が設定されていません")
        return flask.jsonify(error.model_dump()), 503

    # レート制限を適用
    rate_limiter = price_watch.store.amazon.paapi_rate_limiter.get_rate_limiter()
    rate_limiter.acquire()

    # 検索実行
    try:
        results = my_lib.store.amazon.api.search_items(
            config=amazon_api_config,
            keywords=request.keywords,
            item_count=request.item_count,
        )

        items = [
            AmazonSearchResultItem(
                title=item.title,
                asin=item.asin,
                price=item.price,
                thumb_url=item.thumb_url,
            )
            for item in results
        ]

        response = AmazonSearchResponse(items=items)
        return flask.jsonify(response.model_dump())

    except Exception:
        logging.exception("Amazon検索エラー: keywords=%s", request.keywords)
        error = ErrorResponse(error="検索中にエラーが発生しました")
        return flask.jsonify(error.model_dump()), 500
