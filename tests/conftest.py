#!/usr/bin/env python3
# ruff: noqa: S101
"""
共通テストフィクスチャ

テスト全体で使用する共通のフィクスチャとヘルパーを定義します。
"""

import logging
import pathlib
import unittest.mock

import flask
import flask.testing
import pytest

import price_watch.history
import price_watch.webapi.server


# === 環境モック ===
@pytest.fixture(scope="session", autouse=True)
def env_mock():
    """テスト環境用の環境変数モック"""
    with unittest.mock.patch.dict(
        "os.environ",
        {
            "TEST": "true",
            "NO_COLORED_LOGS": "true",
        },
    ) as fixture:
        yield fixture


@pytest.fixture(scope="session", autouse=True)
def slack_mock():
    """Slack API のモック"""
    with (
        unittest.mock.patch(
            "my_lib.notify.slack.slack_sdk.web.client.WebClient.chat_postMessage",
            return_value={"ok": True, "ts": "1234567890.123456"},
        ),
        unittest.mock.patch(
            "my_lib.notify.slack.slack_sdk.web.client.WebClient.files_upload_v2",
            return_value={"ok": True, "files": [{"id": "test_file_id"}]},
        ),
        unittest.mock.patch(
            "my_lib.notify.slack.slack_sdk.web.client.WebClient.files_getUploadURLExternal",
            return_value={"ok": True, "upload_url": "https://example.com"},
        ) as fixture,
    ):
        yield fixture


@pytest.fixture(autouse=True)
def _clear():
    """各テスト前にステートをクリア"""
    import my_lib.notify.slack

    my_lib.notify.slack._interval_clear()
    my_lib.notify.slack._hist_clear()


# === データベースフィクスチャ ===
@pytest.fixture
def temp_data_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """一時データディレクトリを作成"""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


@pytest.fixture
def initialized_db(temp_data_dir: pathlib.Path) -> pathlib.Path:
    """初期化済みの一時データベースを作成"""
    price_watch.history.init(temp_data_dir)
    return temp_data_dir


# === Web API フィクスチャ ===
@pytest.fixture
def app(initialized_db: pathlib.Path, tmp_path: pathlib.Path) -> flask.Flask:
    """Flask アプリケーションフィクスチャ"""
    # テスト用のダミー静的ディレクトリ（存在しないパスでも可）
    static_dir = tmp_path / "static"
    return price_watch.webapi.server.create_app(static_dir_path=static_dir)


@pytest.fixture
def client(app: flask.Flask) -> flask.testing.FlaskClient:
    """Flask テストクライアントフィクスチャ"""
    return app.test_client()


# === テストデータフィクスチャ ===
@pytest.fixture
def sample_item() -> dict:
    """サンプルアイテムデータ

    Note: stock は 0（在庫なし）または 1（在庫あり）のブール値的な値。
    history.insert の時間単位重複排除ロジックは stock=1 の場合のみ
    最安値を保持する。
    """
    return {
        "name": "テスト商品",
        "url": "https://example.com/item/1",
        "store": "test-store.com",
        "price": 1000,
        "stock": 1,
        "thumb_url": None,
    }


@pytest.fixture
def sample_items() -> list[dict]:
    """複数のサンプルアイテムデータ

    Note: stock は 0（在庫なし）または 1（在庫あり）のブール値的な値。
    """
    return [
        {
            "name": "商品A",
            "url": "https://store1.com/item/1",
            "store": "store1.com",
            "price": 1000,
            "stock": 1,
            "thumb_url": None,
        },
        {
            "name": "商品A",  # 同じ名前、異なるストア
            "url": "https://store2.com/item/1",
            "store": "store2.com",
            "price": 900,
            "stock": 1,
            "thumb_url": None,
        },
        {
            "name": "商品B",
            "url": "https://store1.com/item/2",
            "store": "store1.com",
            "price": 2000,
            "stock": 0,  # 在庫切れ
            "thumb_url": None,
        },
    ]


# === Slack 通知検証 ===
@pytest.fixture
def slack_checker():
    """Slack 通知検証ヘルパーを返す"""
    import my_lib.notify.slack

    class SlackChecker:
        def assert_notified(self, message: str, index: int = -1) -> None:
            notify_hist = my_lib.notify.slack._hist_get(is_thread_local=False)
            assert notify_hist, "通知がされていません。"
            assert notify_hist[index].find(message) != -1, f"「{message}」が通知されていません。"

        def assert_not_notified(self) -> None:
            notify_hist = my_lib.notify.slack._hist_get(is_thread_local=False)
            assert notify_hist == [], "通知がされています。"

    return SlackChecker()


# === ロギング設定 ===
logging.getLogger("selenium.webdriver.remote").setLevel(logging.WARNING)
logging.getLogger("selenium.webdriver.common").setLevel(logging.DEBUG)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
