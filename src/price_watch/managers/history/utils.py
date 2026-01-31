#!/usr/bin/env python3
"""履歴 DB ユーティリティ.

ハッシュ生成などのユーティリティ関数を提供します。
"""

from __future__ import annotations

import hashlib


def url_hash(url: str) -> str:
    """URL からハッシュを生成.

    Args:
        url: URL 文字列

    Returns:
        12文字のハッシュ
    """
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def generate_item_key(
    url: str | None = None,
    *,
    search_keyword: str | None = None,
    search_cond: str | None = None,
    store_name: str | None = None,
) -> str:
    """アイテムキーを生成.

    通常ストア: SHA256(url)[:12]
    検索系ストア: SHA256(store_name + ":" + search_keyword)[:12]

    NOTE: search_cond は後方互換性のため引数として残しているが、
          item_key 生成には使用しない。これにより、同じキーワードの検索は
          価格範囲や状態が異なっても同一アイテムとして扱われる。

    store_name を含めることで、同じキーワードでも異なるストア（メルカリ・ラクマ等）
    の検索結果を DB 上で区別できる。

    Args:
        url: URL（通常ストア用）
        search_keyword: 検索キーワード（検索系ストア用）
        search_cond: 未使用（後方互換性のため保持）
        store_name: ストア名（検索系ストア用、ハッシュに含める）

    Returns:
        12文字のハッシュ

    Raises:
        ValueError: url も search_keyword も指定されていない場合
    """
    del search_cond  # 未使用（後方互換性のため引数として保持）

    if search_keyword is not None:
        # 検索系ストア: ストア名 + キーワードからキーを生成
        seed = f"{store_name}:{search_keyword}" if store_name else search_keyword
        return hashlib.sha256(seed.encode()).hexdigest()[:12]
    elif url is not None:
        # 通常ストア: URL からキーを生成
        return url_hash(url)
    else:
        raise ValueError("Either url or search_keyword must be provided")
