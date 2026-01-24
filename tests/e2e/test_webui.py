#!/usr/bin/env python3
# ruff: noqa: S101
"""
WebUI E2E テスト

Playwright を使用して WebUI の E2E テストを実行します。
"""

import logging
import pathlib

import pytest
from playwright.sync_api import expect

# プロジェクトルートの reports/evidence/ に保存
EVIDENCE_DIR = pathlib.Path(__file__).parent.parent.parent / "reports" / "evidence"

# URL プレフィックス
URL_PREFIX = "/price"
PRICE_URL_TMPL = "http://{host}:{port}" + URL_PREFIX


def price_url(host, port):
    """価格履歴ページの URL を生成"""
    return PRICE_URL_TMPL.format(host=host, port=port)


@pytest.mark.e2e
class TestWebuiE2E:
    """WebUI E2E テスト"""

    def test_price_page_loads(self, page, host, port):
        """価格履歴ページ表示の E2E テスト

        1. 価格履歴ページにアクセス
        2. ページが正常にロードされることを確認
        """
        page.set_viewport_size({"width": 1920, "height": 1080})

        # コンソールログをキャプチャ
        console_errors = []
        page.on(
            "console",
            lambda message: (
                console_errors.append(message.text) if message.type == "error" else logging.info(message.text)
            ),
        )

        # 価格履歴ページにアクセス
        page.goto(price_url(host, port), wait_until="domcontentloaded")

        # ページタイトルを確認
        expect(page).to_have_title("Price Watch")

        # スクリーンショットを保存
        screenshot_path = EVIDENCE_DIR / "e2e_price_page.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_path), full_page=True)

    def test_price_page_charts(self, page, host, port):
        """価格履歴ページのチャート表示テスト

        1. 価格履歴ページにアクセス
        2. チャートが表示されることを確認
        """
        page.set_viewport_size({"width": 1920, "height": 1080})

        page.goto(price_url(host, port), wait_until="domcontentloaded")

        # Chart.js のキャンバス要素が存在することを確認
        canvas_elements = page.locator("canvas")

        # チャートが1つ以上存在（ローディング完了まで待機）
        expect(canvas_elements.first).to_be_visible(timeout=30000)

    def test_price_page_period_selector(self, page, host, port):
        """期間セレクタのテスト

        1. 価格履歴ページにアクセス
        2. 期間セレクタが存在し、機能することを確認
        """
        page.set_viewport_size({"width": 1920, "height": 1080})

        page.goto(price_url(host, port), wait_until="domcontentloaded")

        # 期間セレクタのボタンが存在することを確認
        period_button = page.locator("button:has-text('30日')")
        expect(period_button).to_be_visible(timeout=10000)

    def test_api_items(self, page, host, port):
        """アイテム一覧 API のテスト"""
        response = page.request.get(f"http://{host}:{port}{URL_PREFIX}/api/items")

        assert response.ok
        data = response.json()
        assert "items" in data

    def test_api_items_with_days(self, page, host, port):
        """アイテム一覧 API（期間指定）のテスト"""
        response = page.request.get(f"http://{host}:{port}{URL_PREFIX}/api/items?days=30")

        assert response.ok
        data = response.json()
        assert "items" in data

    def test_api_item_history(self, page, host, port):
        """アイテム別価格履歴 API のテスト"""
        # まずアイテム一覧を取得
        items_response = page.request.get(f"http://{host}:{port}{URL_PREFIX}/api/items")
        items_data = items_response.json()

        if len(items_data.get("items", [])) == 0:
            pytest.skip("No items available for history test")

        # 最初のアイテムの最初のストアの url_hash を取得
        first_item = items_data["items"][0]
        if "stores" not in first_item or len(first_item["stores"]) == 0:
            pytest.skip("No stores available for history test")

        url_hash = first_item["stores"][0]["url_hash"]
        response = page.request.get(f"http://{host}:{port}{URL_PREFIX}/api/items/{url_hash}/history")

        assert response.ok
        data = response.json()
        assert "history" in data

    def test_api_response_structure(self, page, host, port):
        """API レスポンス構造のテスト（複数ストア対応）"""
        response = page.request.get(f"http://{host}:{port}{URL_PREFIX}/api/items")

        assert response.ok
        data = response.json()
        assert "items" in data
        assert "store_definitions" in data

        # アイテムがある場合、構造を確認
        if len(data["items"]) > 0:
            item = data["items"][0]
            assert "name" in item
            assert "stores" in item
            assert "best_store" in item
            assert "best_effective_price" in item

            # ストアエントリの構造を確認
            if len(item["stores"]) > 0:
                store = item["stores"][0]
                assert "url_hash" in store
                assert "store" in store
                assert "current_price" in store
                assert "effective_price" in store
                assert "point_rate" in store

    def test_price_page_no_js_errors(self, page, host, port):
        """JavaScript エラーがないことを確認

        1. 価格履歴ページにアクセス
        2. JavaScript エラーがないことを確認
        """
        page.set_viewport_size({"width": 1920, "height": 1080})

        js_errors = []
        page.on("pageerror", lambda error: js_errors.append(str(error)))

        page.goto(price_url(host, port), wait_until="domcontentloaded")

        # ページのロード完了を待機
        page.wait_for_load_state("load")

        # JavaScript エラーがないこと
        assert len(js_errors) == 0, f"JavaScript エラーが発生しました: {js_errors}"

    def test_item_cards_displayed(self, page, host, port):
        """アイテムカードが表示されることを確認

        1. 価格履歴ページにアクセス
        2. アイテムカードが表示されることを確認
        """
        page.set_viewport_size({"width": 1920, "height": 1080})

        page.goto(price_url(host, port), wait_until="domcontentloaded")

        # アイテムカードが存在することを確認（ローディング完了まで待機）
        item_cards = page.locator("div.bg-white.rounded-lg.shadow")
        expect(item_cards.first).to_be_visible(timeout=30000)
