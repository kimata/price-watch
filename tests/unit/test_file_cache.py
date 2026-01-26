#!/usr/bin/env python3
# ruff: noqa: S101
"""
file_cache モジュールのユニットテスト

ファイルキャッシュ機構を検証します。
"""

from __future__ import annotations

import pathlib
import threading
import time

import pytest

from price_watch.file_cache import FileCache


class TestFileCache:
    """FileCache クラスのテスト"""

    def test_get_returns_none_when_file_not_exists(self, tmp_path: pathlib.Path) -> None:
        """ファイルが存在しない場合は None を返す"""
        non_existent = tmp_path / "non_existent.txt"
        cache: FileCache[str] = FileCache(non_existent, lambda p: p.read_text())

        result = cache.get()

        assert result is None

    def test_get_loads_file_on_first_access(self, tmp_path: pathlib.Path) -> None:
        """初回アクセス時にファイルを読み込む"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello world")

        cache: FileCache[str] = FileCache(file_path, lambda p: p.read_text())

        result = cache.get()

        assert result == "hello world"

    def test_get_uses_cache_on_subsequent_access(self, tmp_path: pathlib.Path) -> None:
        """2回目以降はキャッシュを使用"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("initial content")

        load_count = 0

        def counting_loader(p: pathlib.Path) -> str:
            nonlocal load_count
            load_count += 1
            return p.read_text()

        cache: FileCache[str] = FileCache(file_path, counting_loader)

        # 3回アクセス
        cache.get()
        cache.get()
        cache.get()

        # loader は1回だけ呼ばれる
        assert load_count == 1

    def test_get_reloads_when_file_modified(self, tmp_path: pathlib.Path) -> None:
        """ファイルが更新されたら再読み込み"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("version 1")

        cache: FileCache[str] = FileCache(file_path, lambda p: p.read_text())

        # 初回読み込み
        result1 = cache.get()
        assert result1 == "version 1"

        # ファイルを更新（mtime を確実に変更するため少し待つ）
        time.sleep(0.01)
        file_path.write_text("version 2")

        # 再読み込みされる
        result2 = cache.get()
        assert result2 == "version 2"

    def test_get_does_not_reload_if_mtime_unchanged(self, tmp_path: pathlib.Path) -> None:
        """mtime が変わらなければ再読み込みしない"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

        load_count = 0

        def counting_loader(p: pathlib.Path) -> str:
            nonlocal load_count
            load_count += 1
            return p.read_text()

        cache: FileCache[str] = FileCache(file_path, counting_loader)

        # 複数回アクセス
        for _ in range(5):
            cache.get()

        # loader は1回だけ
        assert load_count == 1

    def test_invalidate_clears_cache(self, tmp_path: pathlib.Path) -> None:
        """invalidate でキャッシュをクリア"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

        load_count = 0

        def counting_loader(p: pathlib.Path) -> str:
            nonlocal load_count
            load_count += 1
            return p.read_text()

        cache: FileCache[str] = FileCache(file_path, counting_loader)

        # 初回読み込み
        cache.get()
        assert load_count == 1

        # キャッシュ無効化
        cache.invalidate()

        # 再度アクセスすると再読み込み
        cache.get()
        assert load_count == 2

    def test_invalidate_resets_mtime(self, tmp_path: pathlib.Path) -> None:
        """invalidate は mtime もリセット"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

        cache: FileCache[str] = FileCache(file_path, lambda p: p.read_text())
        cache.get()

        # 内部状態を確認
        assert cache._mtime > 0

        cache.invalidate()

        assert cache._mtime == 0.0
        assert cache._data is None

    def test_thread_safety(self, tmp_path: pathlib.Path) -> None:
        """スレッドセーフであることを確認"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("thread safe content")

        cache: FileCache[str] = FileCache(file_path, lambda p: p.read_text())

        results: list[str | None] = []
        errors: list[Exception] = []

        def read_cache() -> None:
            try:
                for _ in range(100):
                    result = cache.get()
                    if result:
                        results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_cache) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # エラーなし
        assert not errors
        # 全て同じ内容
        assert all(r == "thread safe content" for r in results)

    def test_generic_type(self, tmp_path: pathlib.Path) -> None:
        """ジェネリック型として動作"""
        file_path = tmp_path / "data.json"
        file_path.write_text('{"key": "value"}')

        import json

        cache: FileCache[dict[str, str]] = FileCache(file_path, lambda p: json.loads(p.read_text()))

        result = cache.get()

        assert result == {"key": "value"}

    def test_loader_exception_propagates(self, tmp_path: pathlib.Path) -> None:
        """loader で例外が発生した場合は伝播"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

        def failing_loader(_: pathlib.Path) -> str:
            raise ValueError("Load failed")

        cache: FileCache[str] = FileCache(file_path, failing_loader)

        with pytest.raises(ValueError, match="Load failed"):
            cache.get()
