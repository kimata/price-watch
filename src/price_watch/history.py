#!/usr/bin/env python3
"""価格履歴ユーティリティ.

履歴管理の実装は managers/history/ に移行しました。
このモジュールはユーティリティ関数のみを提供します。
"""

from price_watch.managers.history import generate_item_key, url_hash

__all__ = ["generate_item_key", "url_hash"]
