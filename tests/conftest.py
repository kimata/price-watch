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
import my_lib.pytest_util
import pytest

import price_watch.managers.history
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
    """一時データディレクトリを作成（ワーカー固有）"""
    # pytest-xdist 並列実行時はワーカーIDをディレクトリ名に付加
    data_dir = my_lib.pytest_util.get_path(tmp_path / "data")
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


@pytest.fixture
def history_manager(temp_data_dir: pathlib.Path) -> price_watch.managers.history.HistoryManager:
    """初期化済みの HistoryManager を作成"""
    manager = price_watch.managers.history.HistoryManager.create(temp_data_dir)
    manager.initialize()
    return manager


@pytest.fixture
def initialized_db(
    history_manager: price_watch.managers.history.HistoryManager,
) -> price_watch.managers.history.HistoryManager:
    """初期化済みの HistoryManager を返す（後方互換性のため）"""
    return history_manager


# === Web API フィクスチャ ===
@pytest.fixture
def app(
    history_manager: price_watch.managers.history.HistoryManager,
    tmp_path: pathlib.Path,
) -> flask.Flask:
    """Flask アプリケーションフィクスチャ"""
    # テスト用のダミー静的ディレクトリ（存在しないパスでも可）
    static_dir = tmp_path / "static"
    app = price_watch.webapi.server.create_app(static_dir_path=static_dir)
    # テスト用の HistoryManager をアプリケーションコンテキストに保存
    app.config["history_manager"] = history_manager
    return app


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


# === OGP フォントフィクスチャ ===
@pytest.fixture(scope="session")
def font_paths() -> "price_watch.webapi.ogp.FontPaths":
    """OGP 画像生成用フォントパスを取得

    1. config.yaml からフォント設定を読み込む
    2. 見つからない場合はシステムフォントを探す
    3. それでも見つからない場合は空の FontPaths を返す
    """
    import price_watch.config
    import price_watch.webapi.ogp

    # config.yaml からフォント設定を読み込む
    config_path = pathlib.Path("config.yaml")
    if config_path.exists():
        config = price_watch.config.load(config_path)
        if config.font is not None:
            font_paths = price_watch.webapi.ogp.FontPaths.from_config(config.font)
            # フォントファイルが存在するか確認
            if font_paths.jp_medium is not None and font_paths.jp_medium.exists():
                return font_paths

    # フォールバック: システムフォントを探す
    for font_path in price_watch.webapi.ogp.JAPANESE_FONT_PATHS:
        if pathlib.Path(font_path).exists():
            path = pathlib.Path(font_path)
            return price_watch.webapi.ogp.FontPaths(
                jp_regular=path,
                jp_medium=path,
                jp_bold=path,
                en_medium=path,
                en_bold=path,
            )

    # フォントが見つからない場合は空の FontPaths を返す
    return price_watch.webapi.ogp.FontPaths()


# === ロギング設定 ===
logging.getLogger("selenium.webdriver.remote").setLevel(logging.WARNING)
logging.getLogger("selenium.webdriver.common").setLevel(logging.DEBUG)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
