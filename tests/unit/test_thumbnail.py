#!/usr/bin/env python3
# ruff: noqa: S101
"""
thumbnail.py のユニットテスト
"""

from price_watch.thumbnail import (
    get_thumb_filename,
    get_thumb_url,
)


class TestThumbnail:
    """サムネイル関連のテスト"""

    def test_get_thumb_filename(self):
        """ファイル名生成"""
        filename = get_thumb_filename("Test Item")

        # SHA256 の先頭16文字 + .png
        assert filename.endswith(".png")
        assert len(filename) == 16 + 4  # hash + ".png"

    def test_get_thumb_filename_consistent(self):
        """同じ入力で同じファイル名が生成されること"""
        filename1 = get_thumb_filename("Test Item")
        filename2 = get_thumb_filename("Test Item")

        assert filename1 == filename2

    def test_get_thumb_filename_different(self):
        """異なる入力で異なるファイル名が生成されること"""
        filename1 = get_thumb_filename("Test Item 1")
        filename2 = get_thumb_filename("Test Item 2")

        assert filename1 != filename2

    def test_get_thumb_url(self):
        """URL 生成"""
        url = get_thumb_url("Test Item")

        assert url.startswith("/price/thumb/")
        assert url.endswith(".png")

    def test_get_thumb_url_format(self):
        """URL フォーマット"""
        url = get_thumb_url("Test Item")
        filename = get_thumb_filename("Test Item")

        assert url == f"/price/thumb/{filename}"
