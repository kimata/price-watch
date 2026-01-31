"""パスワードハッシュユーティリティ.

SHA-256 を使用したパスワードハッシュの生成と検証を提供します。

使用例（ハッシュの生成）:
    echo "your_password" | uv run python -m price_watch.webapi.password
"""

import hashlib
import hmac

# アプリケーション固有のソルト（変更しないこと）
_SALT = "price-watch-editor-v1"


def generate_hash(password: str) -> str:
    """パスワードから SHA-256 ハッシュを生成.

    Args:
        password: 平文パスワード

    Returns:
        16進数形式のハッシュ文字列
    """
    salted = f"{_SALT}:{password}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """パスワードがハッシュと一致するか検証.

    タイミング攻撃を防ぐため、hmac.compare_digest を使用。

    Args:
        password: 検証する平文パスワード
        password_hash: 保存されているハッシュ

    Returns:
        一致する場合 True
    """
    computed_hash = generate_hash(password)
    return hmac.compare_digest(computed_hash, password_hash)


if __name__ == "__main__":
    import sys

    # 標準入力からパスワードを読み取り（改行を除去）
    password = sys.stdin.read().strip()
    if not password:
        print("Usage: echo 'your_password' | python -m price_watch.webapi.password", file=sys.stderr)
        sys.exit(1)

    print(generate_hash(password))
