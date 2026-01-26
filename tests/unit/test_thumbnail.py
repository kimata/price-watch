#!/usr/bin/env python3
# ruff: noqa: S101
"""
thumbnail モジュールのユニットテスト

サムネイル画像管理を検証します。
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import PIL.Image
import requests

import price_watch.thumbnail


class TestInit:
    """init 関数のテスト"""

    def test_init_sets_thumb_path(self, tmp_path: Path) -> None:
        """サムネイルパスを設定"""
        custom_path = tmp_path / "thumbs"
        price_watch.thumbnail.init(custom_path)
        assert price_watch.thumbnail._thumb_path == custom_path

    def test_init_with_none_keeps_default(self) -> None:
        """None の場合はデフォルトを維持"""
        original = price_watch.thumbnail._thumb_path
        price_watch.thumbnail.init(None)
        assert price_watch.thumbnail._thumb_path == original


class TestGetThumbDir:
    """get_thumb_dir 関数のテスト"""

    def test_returns_thumb_path(self, tmp_path: Path) -> None:
        """サムネイルディレクトリを返す"""
        price_watch.thumbnail.init(tmp_path)
        result = price_watch.thumbnail.get_thumb_dir()
        assert result == tmp_path


class TestGetThumbFilename:
    """get_thumb_filename 関数のテスト"""

    def test_returns_hashed_filename(self) -> None:
        """ハッシュ化されたファイル名を返す"""
        result = price_watch.thumbnail.get_thumb_filename("テスト商品")
        assert result.endswith(".png")
        assert len(result) == 16 + 4  # hash(16) + ".png"(4)

    def test_same_name_returns_same_filename(self) -> None:
        """同じ名前は同じファイル名を返す"""
        result1 = price_watch.thumbnail.get_thumb_filename("テスト商品")
        result2 = price_watch.thumbnail.get_thumb_filename("テスト商品")
        assert result1 == result2

    def test_different_names_return_different_filenames(self) -> None:
        """異なる名前は異なるファイル名を返す"""
        result1 = price_watch.thumbnail.get_thumb_filename("商品A")
        result2 = price_watch.thumbnail.get_thumb_filename("商品B")
        assert result1 != result2


class TestGetThumbPath:
    """get_thumb_path 関数のテスト"""

    def test_returns_full_path(self, tmp_path: Path) -> None:
        """フルパスを返す"""
        price_watch.thumbnail.init(tmp_path)
        result = price_watch.thumbnail.get_thumb_path("テスト商品")
        assert result.parent == tmp_path
        assert result.suffix == ".png"


class TestGetThumbUrl:
    """get_thumb_url 関数のテスト"""

    def test_returns_api_url(self) -> None:
        """API URL を返す"""
        result = price_watch.thumbnail.get_thumb_url("テスト商品")
        assert result.startswith("/price/thumb/")
        assert result.endswith(".png")

    def test_url_matches_filename(self) -> None:
        """URL がファイル名と一致"""
        filename = price_watch.thumbnail.get_thumb_filename("Test Item")
        url = price_watch.thumbnail.get_thumb_url("Test Item")
        assert url == f"/price/thumb/{filename}"


class TestThumbExists:
    """thumb_exists 関数のテスト"""

    def test_returns_true_when_exists(self, tmp_path: Path) -> None:
        """ファイルが存在する場合は True"""
        price_watch.thumbnail.init(tmp_path)
        # ファイルを作成
        thumb_path = price_watch.thumbnail.get_thumb_path("テスト商品")
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.write_bytes(b"dummy")

        assert price_watch.thumbnail.thumb_exists("テスト商品") is True

    def test_returns_false_when_not_exists(self, tmp_path: Path) -> None:
        """ファイルが存在しない場合は False"""
        price_watch.thumbnail.init(tmp_path)
        assert price_watch.thumbnail.thumb_exists("存在しない商品") is False


class TestSaveThumb:
    """save_thumb 関数のテスト"""

    def test_skips_when_exists(self, tmp_path: Path) -> None:
        """既存ファイルがある場合はスキップ"""
        price_watch.thumbnail.init(tmp_path)

        # ファイルを作成
        thumb_path = price_watch.thumbnail.get_thumb_path("テスト商品")
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.write_bytes(b"dummy")

        result = price_watch.thumbnail.save_thumb("テスト商品", "https://example.com/img.jpg")

        # URL を返す（ダウンロードはしない）
        assert result == price_watch.thumbnail.get_thumb_url("テスト商品")

    def test_downloads_and_saves(self, tmp_path: Path) -> None:
        """画像をダウンロードして保存"""
        price_watch.thumbnail.init(tmp_path)

        # テスト用の画像を作成
        img = PIL.Image.new("RGB", (100, 100), color="red")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        mock_response = MagicMock()
        mock_response.content = img_bytes.read()
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            result = price_watch.thumbnail.save_thumb("新商品", "https://example.com/img.png")

        assert result == price_watch.thumbnail.get_thumb_url("新商品")
        assert price_watch.thumbnail.thumb_exists("新商品")

    def test_converts_to_rgba(self, tmp_path: Path) -> None:
        """RGBA に変換"""
        price_watch.thumbnail.init(tmp_path)

        # RGB 画像を作成
        img = PIL.Image.new("RGB", (100, 100), color="blue")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        mock_response = MagicMock()
        mock_response.content = img_bytes.read()
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            price_watch.thumbnail.save_thumb("RGB商品", "https://example.com/img.png")

        # 保存された画像を確認
        saved_path = price_watch.thumbnail.get_thumb_path("RGB商品")
        saved_img = PIL.Image.open(saved_path)
        assert saved_img.mode == "RGBA"

    def test_resizes_large_image(self, tmp_path: Path) -> None:
        """大きな画像をリサイズ"""
        price_watch.thumbnail.init(tmp_path)

        # 大きな画像を作成
        img = PIL.Image.new("RGB", (1000, 1000), color="green")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        mock_response = MagicMock()
        mock_response.content = img_bytes.read()
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            price_watch.thumbnail.save_thumb("大きい商品", "https://example.com/img.png")

        # 保存された画像を確認
        saved_path = price_watch.thumbnail.get_thumb_path("大きい商品")
        saved_img = PIL.Image.open(saved_path)
        # THUMB_SIZE (200, 200) 以下になっている
        assert saved_img.width <= 200
        assert saved_img.height <= 200

    def test_handles_request_error(self, tmp_path: Path) -> None:
        """リクエストエラーをハンドル"""
        price_watch.thumbnail.init(tmp_path)

        with patch("requests.get", side_effect=requests.RequestException("Network error")):
            result = price_watch.thumbnail.save_thumb("エラー商品", "https://example.com/img.png")

        assert result is None

    def test_handles_image_error(self, tmp_path: Path) -> None:
        """画像処理エラーをハンドル"""
        price_watch.thumbnail.init(tmp_path)

        mock_response = MagicMock()
        mock_response.content = b"invalid image data"
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            result = price_watch.thumbnail.save_thumb("無効画像", "https://example.com/img.png")

        assert result is None

    def test_creates_directory(self, tmp_path: Path) -> None:
        """ディレクトリを作成"""
        nested_path = tmp_path / "nested" / "thumbs"
        price_watch.thumbnail.init(nested_path)

        # テスト用の画像を作成
        img = PIL.Image.new("RGB", (50, 50), color="yellow")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        mock_response = MagicMock()
        mock_response.content = img_bytes.read()
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            result = price_watch.thumbnail.save_thumb("ネスト商品", "https://example.com/img.png")

        assert result is not None
        assert nested_path.exists()
