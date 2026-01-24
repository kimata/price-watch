#!/usr/bin/env python3
"""定数定義."""

from __future__ import annotations

import pathlib

# パス
DATA_PATH = pathlib.Path(__file__).parent.parent.parent / "data"
DUMP_PATH = DATA_PATH / "debug"
THUMB_PATH = DATA_PATH / "thumb"
DB_FILE = "price_history.db"

# 監視間隔
SLEEP_UNIT = 60
SCRAPE_INTERVAL_SEC = 5

# エラー通知
ERROR_NOTIFY_COUNT = 6
