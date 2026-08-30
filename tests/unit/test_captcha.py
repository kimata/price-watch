#!/usr/bin/env python3
"""
captcha.py のユニットテスト

CAPTCHA 解決処理を検証します。
実際の reCAPTCHA 解決ロジックは my_lib.store.captcha.resolve_recaptcha_auto に
移譲されているため、ここでは委譲が正しく行われることを検証します。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import price_watch.captcha


class TestResolveMp3:
    """resolve_mp3 関数のテスト"""

    def test_delegates_to_my_lib(self) -> None:
        """my_lib.store.captcha.resolve_recaptcha_auto に委譲する"""
        mock_page = MagicMock()

        with patch("my_lib.store.captcha.resolve_recaptcha_auto") as mock_resolve:
            price_watch.captcha.resolve_mp3(mock_page)

        mock_resolve.assert_called_once_with(mock_page)
