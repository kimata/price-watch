#!/usr/bin/env python3
"""CAPTCHA 解決処理."""

from __future__ import annotations

from typing import TYPE_CHECKING

import my_lib.store.captcha

if TYPE_CHECKING:
    from my_lib.browser import Page


def resolve_mp3(page: Page) -> None:
    """reCAPTCHA を音声認識で解決.

    共有実装 my_lib.store.captcha.resolve_recaptcha_auto へ委譲する。
    """
    my_lib.store.captcha.resolve_recaptcha_auto(page)
