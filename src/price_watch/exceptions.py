#!/usr/bin/env python3
"""Price Watch 例外階層.

アプリケーション固有の例外クラスを定義します。
"""

from __future__ import annotations


class PriceWatchError(Exception):
    """Price Watch 基底例外.

    アプリケーション固有の全ての例外の基底クラス。
    """


class ConfigError(PriceWatchError):
    """設定エラー.

    設定ファイルの読み込みやバリデーションに失敗した場合。
    """


class ScrapeError(PriceWatchError):
    """スクレイピングエラー.

    スクレイピング処理全般に関連するエラーの基底クラス。
    """


class CrawlError(ScrapeError):
    """クロール処理エラー.

    ページの取得、パース、価格抽出などのクロール処理に失敗した場合。
    """


class SessionError(ScrapeError):
    """Selenium セッションエラー.

    WebDriver セッションが無効になった場合。
    """


class PaapiError(PriceWatchError):
    """Amazon PA-API エラー.

    PA-API 呼び出しに失敗した場合。
    """


class NotificationError(PriceWatchError):
    """通知送信エラー.

    Slack 通知の送信に失敗した場合。
    """


class HistoryError(PriceWatchError):
    """履歴 DB エラー.

    履歴データベースの操作に失敗した場合。
    """


class BrowserError(PriceWatchError):
    """ブラウザエラー.

    ブラウザの起動、操作、終了に失敗した場合。
    """
