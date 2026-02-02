#!/usr/bin/env python3
"""ヨドバシ検索 API エンドポイント.

my_lib.store.yodobashi.search を使用したキーワード検索機能を提供します。
"""

import logging
import threading

import flask
import my_lib.store.yodobashi
import selenium.webdriver.support.wait
from pydantic import BaseModel, Field

import price_watch.webapi.cache

blueprint = flask.Blueprint("yodobashi_search", __name__)

# 検索時の排他制御用ロック
_search_lock = threading.Lock()


class YodobashiSearchRequest(BaseModel):
    """ヨドバシ検索リクエスト."""

    keywords: str = Field(..., min_length=1, max_length=200, description="検索キーワード")
    item_count: int = Field(default=10, ge=1, le=20, description="取得件数（1-20）")


class YodobashiSearchResultItem(BaseModel):
    """ヨドバシ検索結果アイテム."""

    name: str
    url: str
    price: int | None
    thumb_url: str | None


class YodobashiSearchResponse(BaseModel):
    """ヨドバシ検索レスポンス."""

    items: list[YodobashiSearchResultItem]


class ErrorResponse(BaseModel):
    """エラーレスポンス."""

    error: str


def _is_yodobashi_search_available() -> bool:
    """ヨドバシ検索が利用可能かどうかを判定.

    設定ファイルが読み込める場合に利用可能とする。
    """
    app_config = price_watch.webapi.cache.get_app_config()
    return app_config is not None


@blueprint.route("/api/yodobashi/search/available", methods=["GET"])
def check_available() -> flask.Response:
    """ヨドバシ検索 API が利用可能かどうかを返す."""
    available = _is_yodobashi_search_available()
    return flask.jsonify({"available": available})


@blueprint.route("/api/yodobashi/search", methods=["POST"])
def search() -> flask.Response | tuple[flask.Response, int]:
    """ヨドバシ商品をキーワードで検索."""
    # リクエストのバリデーション
    try:
        data = flask.request.get_json()
        if data is None:
            error = ErrorResponse(error="リクエストボディが必要です")
            return flask.jsonify(error.model_dump()), 400

        request = YodobashiSearchRequest.model_validate(data)
    except Exception as e:
        logging.warning("ヨドバシ検索リクエストのバリデーションエラー: %s", e)
        error = ErrorResponse(error="リクエストの形式が正しくありません")
        return flask.jsonify(error.model_dump()), 400

    # 排他制御: 同時に1リクエストのみ処理
    if not _search_lock.acquire(blocking=False):
        error = ErrorResponse(error="他の検索リクエストを処理中です。しばらくしてから再試行してください。")
        return flask.jsonify(error.model_dump()), 503

    try:
        # WebDriver を取得
        driver = price_watch.webapi.cache.get_yodobashi_driver()
        if driver is None:
            error = ErrorResponse(error="WebDriver の初期化に失敗しました")
            return flask.jsonify(error.model_dump()), 503

        # WebDriverWait を作成
        wait = selenium.webdriver.support.wait.WebDriverWait(driver, 10)

        # 検索実行
        try:
            results = my_lib.store.yodobashi.search(
                driver,
                wait,
                request.keywords,
                max_items=request.item_count,
            )

            items = [
                YodobashiSearchResultItem(
                    name=item.name,
                    url=item.url,
                    price=item.price,
                    thumb_url=item.thumb_url,
                )
                for item in results
            ]

            response = YodobashiSearchResponse(items=items)
            return flask.jsonify(response.model_dump())

        except Exception:
            logging.exception("ヨドバシ検索エラー: keywords=%s", request.keywords)
            error = ErrorResponse(error="検索中にエラーが発生しました")
            return flask.jsonify(error.model_dump()), 500

    finally:
        _search_lock.release()
