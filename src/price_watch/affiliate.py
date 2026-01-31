#!/usr/bin/env python3
"""アフィリエイトID処理ユーティリティ."""

from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from price_watch.target import CheckMethod


def append_affiliate_id(url: str, affiliate_id: str | None, check_method: CheckMethod) -> str:
    """URLにアフィリエイトIDを追加.

    Args:
        url: 対象URL
        affiliate_id: アフィリエイトID（None の場合は何もしない）
        check_method: チェックメソッド（ストアの種類を判定）

    Returns:
        アフィリエイトID付きURL（既存パラメータがある場合は変更なし）
    """
    if not affiliate_id or not url:
        return url

    import price_watch.target

    # ストア種別に応じたパラメータ名を決定
    match check_method:
        case (
            price_watch.target.CheckMethod.MERCARI_SEARCH
            | price_watch.target.CheckMethod.RAKUMA_SEARCH
            | price_watch.target.CheckMethod.PAYPAY_SEARCH
        ):
            param_name = "afid"
        case price_watch.target.CheckMethod.AMAZON_PAAPI:
            param_name = "tag"
        case _:
            # 対応していないストアの場合は URL をそのまま返す
            return url

    parsed = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed.query)

    # 既存パラメータは上書きしない
    if param_name in query_params:
        return url

    # 新しいクエリストリングを構築
    new_query = urllib.parse.urlencode({param_name: affiliate_id})
    if parsed.query:
        new_query = f"{parsed.query}&{new_query}"

    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
    )
