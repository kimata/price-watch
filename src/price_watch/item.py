#!/usr/bin/env python3
"""アイテムリスト管理."""

from __future__ import annotations

from typing import Any

import price_watch.target


def load_resolved_items(
    target_file: str = price_watch.target.TARGET_FILE_PATH,
) -> list[price_watch.target.ResolvedItem]:
    """監視対象アイテムリストを ResolvedItem として読み込む.

    Args:
        target_file: ターゲット設定ファイルパス
    """
    config = price_watch.target.load(target_file)
    return config.resolve_items()


def load_item_list(
    error_count: dict[str, int], target_file: str = price_watch.target.TARGET_FILE_PATH
) -> list[dict[str, Any]]:
    """監視対象アイテムリストを読み込む（後方互換性のため dict 形式）.

    Args:
        error_count: エラーカウント辞書
        target_file: ターゲット設定ファイルパス
    """
    items = load_resolved_items(target_file)
    result: list[dict[str, Any]] = []

    for item in items:
        item_dict = item.to_dict()

        if item_dict["url"] not in error_count:
            error_count[item_dict["url"]] = 0

        result.append(item_dict)

    return result


def get_target_urls(target_file: str = price_watch.target.TARGET_FILE_PATH) -> set[str]:
    """監視対象URLのセットを取得.

    Args:
        target_file: ターゲット設定ファイルパス
    """
    items = load_resolved_items(target_file)
    return {item.url for item in items}
