"""パスワードハッシュユーティリティ.

Argon2id を使用したパスワードハッシュの生成と検証を提供します。

使用例（ハッシュの生成）:
    echo "your_password" | uv run python -m price_watch.webapi.password
"""

import argon2

# Argon2 ハッシャー（OWASP 推奨パラメータ）
# https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
_hasher = argon2.PasswordHasher(
    time_cost=3,  # 反復回数
    memory_cost=65536,  # 64MB
    parallelism=4,  # 並列度
    hash_len=32,  # ハッシュ長
    salt_len=16,  # ソルト長
)


def generate_hash(password: str) -> str:
    """パスワードから Argon2id ハッシュを生成.

    Args:
        password: 平文パスワード

    Returns:
        Argon2id 形式のハッシュ文字列（$argon2id$... の形式）
    """
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """パスワードがハッシュと一致するか検証.

    Args:
        password: 検証する平文パスワード
        password_hash: 保存されているハッシュ

    Returns:
        一致する場合 True
    """
    try:
        _hasher.verify(password_hash, password)
        return True
    except argon2.exceptions.VerifyMismatchError:
        return False
    except argon2.exceptions.InvalidHashError:
        return False


if __name__ == "__main__":
    import sys

    # 標準入力からパスワードを読み取り（改行を除去）
    password = sys.stdin.read().strip()
    if not password:
        print("Usage: echo 'your_password' | python -m price_watch.webapi.password", file=sys.stderr)
        sys.exit(1)

    print(generate_hash(password))
