#!/usr/bin/env python3
"""アイテムリスト管理."""

from __future__ import annotations

import pathlib

import price_watch.target


def _load_resolved_items(
    target_file: pathlib.Path | None = None,
) -> list[price_watch.target.ResolvedItem]:
    """監視対象アイテムリストを ResolvedItem として読み込む.

    Args:
        target_file: ターゲット設定ファイルパス。省略時は TARGET_FILE_PATH を使用。
    """
    config = price_watch.target.load(target_file)
    return config.resolve_items()


def get_target_urls(target_file: pathlib.Path | None = None) -> set[str]:
    """監視対象URLのセットを取得.

    Args:
        target_file: ターゲット設定ファイルパス。省略時は TARGET_FILE_PATH を使用。
    """
    items = _load_resolved_items(target_file)
    return {item.url for item in items}
