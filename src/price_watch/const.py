#!/usr/bin/env python3
"""定数定義."""

from __future__ import annotations

import pathlib

# パス
DATA_PATH = pathlib.Path(__file__).parent.parent.parent / "data"
DUMP_PATH = DATA_PATH / "debug"
THUMB_PATH = DATA_PATH / "thumb"
DB_FILE = "price.db"

# スキーマファイル
_SCHEMA_DIR = pathlib.Path(__file__).parent.parent.parent / "schema"
SCHEMA_SQLITE_HISTORY = _SCHEMA_DIR / "sqlite_history.schema"
SCHEMA_SQLITE_METRICS = _SCHEMA_DIR / "sqlite_metrics.schema"
SCHEMA_CONFIG = _SCHEMA_DIR / "config.schema"
SCHEMA_TARGET = _SCHEMA_DIR / "target.schema"

# 監視間隔
SLEEP_UNIT = 60
SCRAPE_INTERVAL_SEC = 5

# エラー通知
ERROR_NOTIFY_COUNT = 6
