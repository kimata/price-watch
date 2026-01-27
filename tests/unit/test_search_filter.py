#!/usr/bin/env python3
# ruff: noqa: S101
"""
store/search_filter.py のユニットテスト

検索キーワードの全断片一致フィルタリングを検証します。
"""

from __future__ import annotations

import price_watch.store.search_filter


class TestMatchesAllKeywords:
    """matches_all_keywords 関数のテスト"""

    def test_all_fragments_match(self):
        """全断片が含まれている場合は True"""
        assert price_watch.store.search_filter.matches_all_keywords(
            "MacBook Pro M4 14インチ", "MacBook Pro M4"
        )

    def test_partial_mismatch(self):
        """一部の断片が含まれていない場合は False"""
        assert not price_watch.store.search_filter.matches_all_keywords("MacBook Air M4", "MacBook Pro M4")

    def test_case_insensitive(self):
        """大文字小文字を無視して判定"""
        assert price_watch.store.search_filter.matches_all_keywords("MacBook Pro 14", "macbook pro")

    def test_empty_keyword(self):
        """空キーワードは常に True"""
        assert price_watch.store.search_filter.matches_all_keywords("任意の商品名", "")

    def test_single_keyword(self):
        """単一キーワード"""
        assert price_watch.store.search_filter.matches_all_keywords("MacBook Pro", "MacBook")

    def test_single_keyword_not_found(self):
        """単一キーワードが見つからない"""
        assert not price_watch.store.search_filter.matches_all_keywords("iPad Air", "MacBook")

    def test_whitespace_only_keyword(self):
        """空白のみのキーワードは True"""
        assert price_watch.store.search_filter.matches_all_keywords("商品名", "   ")

    def test_japanese_keywords(self):
        """日本語キーワード"""
        assert price_watch.store.search_filter.matches_all_keywords(
            "ソニー WH-1000XM5 ワイヤレスヘッドホン", "ソニー WH-1000XM5"
        )

    def test_japanese_partial_mismatch(self):
        """日本語キーワードの一部不一致"""
        assert not price_watch.store.search_filter.matches_all_keywords(
            "ソニー WH-1000XM4 ワイヤレスヘッドホン", "ソニー WH-1000XM5"
        )
