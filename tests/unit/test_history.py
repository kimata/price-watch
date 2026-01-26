#!/usr/bin/env python3
# ruff: noqa: S101
"""
history.py のユニットテスト

履歴管理の実装は managers/history/ に移行しました。
このモジュールはユーティリティ関数の再エクスポートのみをテストします。
"""

from __future__ import annotations

import price_watch.history


class TestHistoryReexports:
    """history モジュールの再エクスポートテスト"""

    def test_url_hash_is_exported(self) -> None:
        """url_hash が再エクスポートされている"""
        assert hasattr(price_watch.history, "url_hash")
        # 実際に動作するか確認
        result = price_watch.history.url_hash("https://example.com/item/1")
        assert len(result) == 12

    def test_generate_item_key_is_exported(self) -> None:
        """generate_item_key が再エクスポートされている"""
        assert hasattr(price_watch.history, "generate_item_key")
        # 実際に動作するか確認
        result = price_watch.history.generate_item_key(url="https://example.com/item/1")
        assert len(result) == 12

    def test_all_exports(self) -> None:
        """__all__ が正しい"""
        assert price_watch.history.__all__ == ["generate_item_key", "url_hash"]
