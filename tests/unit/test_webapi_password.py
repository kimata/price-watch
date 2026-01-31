#!/usr/bin/env python3
# ruff: noqa: S101, S105
"""
webapi/password.py のユニットテスト

Argon2id パスワードハッシュの生成と検証を検証します。
"""

from __future__ import annotations

import price_watch.webapi.password


class TestGenerateHash:
    """generate_hash 関数のテスト"""

    def test_generates_argon2id_hash(self):
        """Argon2id 形式のハッシュを生成"""
        password = "test_password"

        result = price_watch.webapi.password.generate_hash(password)

        assert result.startswith("$argon2id$")

    def test_generates_different_hashes_for_same_password(self):
        """同じパスワードでも異なるハッシュを生成（ランダムソルト）"""
        password = "test_password"

        hash1 = price_watch.webapi.password.generate_hash(password)
        hash2 = price_watch.webapi.password.generate_hash(password)

        assert hash1 != hash2

    def test_hash_contains_parameters(self):
        """ハッシュにパラメータが含まれる"""
        password = "test_password"

        result = price_watch.webapi.password.generate_hash(password)

        # m=65536 (memory), t=3 (time), p=4 (parallelism)
        assert "m=65536" in result
        assert "t=3" in result
        assert "p=4" in result


class TestVerifyPassword:
    """verify_password 関数のテスト"""

    def test_verifies_correct_password(self):
        """正しいパスワードで True を返す"""
        password = "correct_password"
        password_hash = price_watch.webapi.password.generate_hash(password)

        result = price_watch.webapi.password.verify_password(password, password_hash)

        assert result is True

    def test_rejects_wrong_password(self):
        """間違ったパスワードで False を返す"""
        password = "correct_password"
        password_hash = price_watch.webapi.password.generate_hash(password)

        result = price_watch.webapi.password.verify_password("wrong_password", password_hash)

        assert result is False

    def test_rejects_invalid_hash_format(self):
        """無効なハッシュ形式で False を返す"""
        result = price_watch.webapi.password.verify_password("password", "invalid_hash")

        assert result is False

    def test_rejects_empty_password(self):
        """空のパスワードでも検証可能（ハッシュが一致すれば True）"""
        password = ""
        password_hash = price_watch.webapi.password.generate_hash(password)

        result = price_watch.webapi.password.verify_password(password, password_hash)

        assert result is True

    def test_rejects_empty_hash(self):
        """空のハッシュで False を返す"""
        result = price_watch.webapi.password.verify_password("password", "")

        assert result is False

    def test_handles_unicode_password(self):
        """Unicode パスワードを正しく処理"""
        password = "パスワード123"
        password_hash = price_watch.webapi.password.generate_hash(password)

        result = price_watch.webapi.password.verify_password(password, password_hash)

        assert result is True

    def test_handles_special_characters(self):
        """特殊文字を含むパスワードを正しく処理"""
        password = "p@ssw0rd!#$%^&*()"
        password_hash = price_watch.webapi.password.generate_hash(password)

        result = price_watch.webapi.password.verify_password(password, password_hash)

        assert result is True

    def test_handles_long_password(self):
        """長いパスワードを正しく処理"""
        password = "a" * 1000
        password_hash = price_watch.webapi.password.generate_hash(password)

        result = price_watch.webapi.password.verify_password(password, password_hash)

        assert result is True
