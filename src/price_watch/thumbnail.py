#!/usr/bin/env python3
"""サムネイル画像管理."""

from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path

import PIL.Image
import requests

import price_watch.const

THUMB_SIZE = (200, 200)
REQUEST_TIMEOUT = 10
MIN_FILE_SIZE_BYTES = 3 * 1024  # 3KB未満はエラー画像とみなす

# モジュールレベルのサムネイルパス（init で設定される）
_thumb_path: Path = price_watch.const.THUMB_PATH


def init(thumb_path: Path | None = None) -> None:
    """サムネイルモジュールを初期化.

    Args:
        thumb_path: サムネイルを保存するディレクトリのパス。省略時はデフォルトを使用。
    """
    global _thumb_path
    if thumb_path is not None:
        _thumb_path = thumb_path


def get_thumb_dir() -> Path:
    """サムネイルディレクトリのパスを取得.

    Returns:
        サムネイルを保存するディレクトリのパス
    """
    return _thumb_path


def get_thumb_filename(item_name: str) -> str:
    """アイテム名から SHA256 ハッシュでファイル名生成.

    Args:
        item_name: アイテム名

    Returns:
        ハッシュ化されたファイル名（拡張子付き）
    """
    hash_value = hashlib.sha256(item_name.encode("utf-8")).hexdigest()[:16]
    return f"{hash_value}.png"


def get_thumb_path(item_name: str) -> Path:
    """サムネイルのパスを取得.

    Args:
        item_name: アイテム名

    Returns:
        サムネイルのパス
    """
    return _thumb_path / get_thumb_filename(item_name)


def get_thumb_url(item_name: str) -> str:
    """API 経由の URL を取得.

    Args:
        item_name: アイテム名

    Returns:
        /price/thumb/{hash}.png 形式の URL
    """
    return f"/price/thumb/{get_thumb_filename(item_name)}"


def thumb_exists(item_name: str) -> bool:
    """サムネイルの存在確認.

    Args:
        item_name: アイテム名

    Returns:
        サムネイルが存在すれば True
    """
    return get_thumb_path(item_name).exists()


def save_thumb(item_name: str, source_url: str) -> str | None:
    """サムネイルをダウンロードして PNG 保存.

    既存ファイルがある場合は更新しない。

    Args:
        item_name: アイテム名
        source_url: サムネイル画像の URL

    Returns:
        保存成功時はローカル URL（/price/thumb/xxx.png）、失敗時は None
    """
    # 既に存在する場合はスキップ
    if thumb_exists(item_name):
        logging.debug("Thumbnail already exists for: %s", item_name)
        return get_thumb_url(item_name)

    try:
        # ディレクトリ作成
        _thumb_path.mkdir(parents=True, exist_ok=True)

        # 画像ダウンロード
        response = requests.get(source_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        # 画像を開いて PNG 形式で保存
        image: PIL.Image.Image = PIL.Image.open(io.BytesIO(response.content))

        # RGBA に変換（透過対応）
        if image.mode != "RGBA":
            image = image.convert("RGBA")

        # リサイズ（アスペクト比維持）
        image.thumbnail(THUMB_SIZE, PIL.Image.Resampling.LANCZOS)

        # 保存
        thumb_path = get_thumb_path(item_name)
        image.save(thumb_path, "PNG", optimize=True)

        # ファイルサイズチェック（3KB未満はエラー画像とみなす）
        file_size = thumb_path.stat().st_size
        if file_size < MIN_FILE_SIZE_BYTES:
            thumb_path.unlink()
            logging.warning(
                "Thumbnail too small (likely placeholder) for %s: %d bytes < %d bytes",
                item_name,
                file_size,
                MIN_FILE_SIZE_BYTES,
            )
            return None

        logging.info("Saved thumbnail for: %s -> %s", item_name, thumb_path)
        return get_thumb_url(item_name)

    except requests.RequestException as e:
        logging.warning("Failed to download thumbnail for %s: %s", item_name, e)
        return None
    except Exception as e:
        logging.warning("Failed to save thumbnail for %s: %s", item_name, e)
        return None
