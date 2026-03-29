#!/usr/bin/env python3
"""クロールログのフォーマット用モジュール.

統一されたログメッセージフォーマットを提供します。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from price_watch.models import CheckedItem
    from price_watch.target import ResolvedItem


# イベント用の絵文字
EMOJI_NEW = "🚀"  # 初回収集
EMOJI_PRICE_DOWN = "📉"  # 価格下落
EMOJI_BACK_IN_STOCK = "✅"  # 在庫復活
EMOJI_OUT_OF_STOCK = "🈚"  # 在庫切れ
EMOJI_IN_STOCK = "📦"  # 在庫あり
EMOJI_CRAWLING = "🔍"  # クロール中

# ANSI エスケープシーケンス
ANSI_RESET = "\033[0m"


def _rgb_to_256(r: int, g: int, b: int) -> int:
    """RGB を 256色パレットの近似色に変換.

    Args:
        r, g, b: 0-255 の RGB 値

    Returns:
        256色パレットのインデックス (16-231: 6x6x6 カラーキューブ)
    """
    # 6x6x6 カラーキューブへの変換（16-231）
    # 各チャンネルを 0-5 の範囲にマッピング
    r_idx = round(r / 255 * 5)
    g_idx = round(g / 255 * 5)
    b_idx = round(b / 255 * 5)
    return 16 + 36 * r_idx + 6 * g_idx + b_idx


def _hex_to_ansi(hex_color: str) -> str:
    """Hex カラーコードを ANSI 256色エスケープシーケンスに変換.

    256色モードは True Color (24-bit) より互換性が高い。

    Args:
        hex_color: "#RRGGBB" 形式のカラーコード

    Returns:
        ANSI 256色エスケープシーケンス
    """
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    color_idx = _rgb_to_256(r, g, b)
    return f"\033[38;5;{color_idx}m"


def _colorize(text: str, color: str | None) -> str:
    """テキストに ANSI カラーを適用.

    Args:
        text: カラーを適用するテキスト
        color: Hex カラーコード（例: "#ff9900"）、None の場合はそのまま返す

    Returns:
        カラー適用済みテキスト
    """
    if color is None:
        return text
    return f"{_hex_to_ansi(color)}{text}{ANSI_RESET}"


def format_item_prefix(item: ResolvedItem | CheckedItem) -> str:
    """アイテムのログプレフィックスを生成.

    Args:
        item: アイテム情報（ResolvedItem または CheckedItem）

    Returns:
        "[ストア名] アイテム名" 形式の文字列（ストア名はカラー付き）
    """
    # ストア名にカラーを適用
    colored_store = _colorize(item.store, item.color)
    return f"[{colored_store}] {item.name}"


def format_crawl_start(item: ResolvedItem | CheckedItem) -> str:
    """クロール開始ログメッセージを生成.

    Args:
        item: アイテム情報（ResolvedItem または CheckedItem）

    Returns:
        フォーマットされたログメッセージ
    """
    prefix = format_item_prefix(item)
    return f"{EMOJI_CRAWLING} {prefix}: クロール開始"


def format_watch_start(item: CheckedItem) -> str:
    """監視開始（初回収集）ログメッセージを生成.

    Args:
        item: チェック済みアイテム

    Returns:
        フォーマットされたログメッセージ
    """
    prefix = format_item_prefix(item)
    if item.stock_as_int() == 1:
        price = item.price or 0
        return f"{EMOJI_NEW} {prefix}: 監視開始 {price}{item.price_unit} (在庫あり)"
    return f"{EMOJI_NEW} {prefix}: 監視開始 (在庫なし)"


def format_price_decrease(item: CheckedItem, old_price: int) -> str:
    """価格下落ログメッセージを生成.

    Args:
        item: チェック済みアイテム
        old_price: 変更前の価格

    Returns:
        フォーマットされたログメッセージ
    """
    prefix = format_item_prefix(item)
    price = item.price or 0
    return f"{EMOJI_PRICE_DOWN} {prefix}: 価格下落 {old_price}{item.price_unit} → {price}{item.price_unit}"


def format_back_in_stock(item: CheckedItem) -> str:
    """在庫復活ログメッセージを生成.

    Args:
        item: チェック済みアイテム

    Returns:
        フォーマットされたログメッセージ
    """
    prefix = format_item_prefix(item)
    price = item.price or 0
    return f"{EMOJI_BACK_IN_STOCK} {prefix}: 在庫復活 {price}{item.price_unit}"


def format_item_status(item: CheckedItem) -> str:
    """アイテム状態ログメッセージを生成.

    Args:
        item: チェック済みアイテム

    Returns:
        フォーマットされたログメッセージ
    """
    prefix = format_item_prefix(item)
    if item.stock_as_int() == 1:
        price = item.price or 0
        return f"{EMOJI_IN_STOCK} {prefix}: {price}{item.price_unit}"
    return f"{EMOJI_OUT_OF_STOCK} {prefix}: 在庫なし"


def format_error(item: ResolvedItem | CheckedItem, error_count: int) -> str:
    """エラーログメッセージを生成.

    Args:
        item: アイテム情報（ResolvedItem または CheckedItem）
        error_count: 連続エラー回数

    Returns:
        フォーマットされたログメッセージ
    """
    prefix = format_item_prefix(item)
    return f"⚠️ {prefix}: エラー発生 (連続{error_count}回目)"
