#!/usr/bin/env python3
"""ファイルキャッシュ機構.

ファイルの更新時刻をチェックし、変更があった場合のみ再読み込みする。
Web サーバーでの設定ファイル読み込みに使用。
"""

from __future__ import annotations

import pathlib
import threading
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class FileCache(Generic[T]):
    """ファイルキャッシュ.

    ファイルの更新時刻をチェックし、変更があった場合のみ再読み込みする。
    スレッドセーフ。
    """

    def __init__(self, file_path: pathlib.Path, loader: Callable[[pathlib.Path], T]) -> None:
        """初期化.

        Args:
            file_path: キャッシュ対象のファイルパス
            loader: ファイルを読み込んでデータを返す関数
        """
        self.file_path = file_path
        self.loader = loader
        self._data: T | None = None
        self._mtime: float = 0.0
        self._lock = threading.Lock()

    def get(self) -> T | None:
        """キャッシュされたデータを取得.

        ファイルが更新されていれば再読み込みする。
        ファイルが存在しない場合は None を返す。

        Returns:
            キャッシュされたデータ、またはファイルが存在しない場合は None
        """
        if not self.file_path.exists():
            return None

        current_mtime = self.file_path.stat().st_mtime

        with self._lock:
            if self._data is None or current_mtime > self._mtime:
                self._data = self.loader(self.file_path)
                self._mtime = current_mtime

            return self._data

    def invalidate(self) -> None:
        """キャッシュを無効化."""
        with self._lock:
            self._data = None
            self._mtime = 0.0
