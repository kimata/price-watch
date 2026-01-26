#!/usr/bin/env python3
# ruff: noqa: S101
"""
captcha.py のユニットテスト

CAPTCHA 解決処理を検証します。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import price_watch.captcha


class TestRecogAudio:
    """_recog_audio 関数のテスト"""

    def test_downloads_and_recognizes_audio(self) -> None:
        """音声をダウンロードして認識"""
        audio_url = "https://example.com/audio.mp3"

        mock_recognizer = MagicMock()
        mock_recognizer.recognize_google.return_value = "hello world"

        with (
            patch("urllib.request.urlretrieve") as mock_urlretrieve,
            patch("pydub.AudioSegment.from_mp3") as mock_from_mp3,
            patch("speech_recognition.Recognizer", return_value=mock_recognizer),
            patch("speech_recognition.AudioFile") as mock_audio_file,
            patch("os.unlink") as mock_unlink,
        ):
            # AudioFile のコンテキストマネージャーをモック
            mock_source = MagicMock()
            mock_audio_file.return_value.__enter__ = MagicMock(return_value=mock_source)
            mock_audio_file.return_value.__exit__ = MagicMock(return_value=False)

            # from_mp3 のチェーンをモック
            mock_audio_segment = MagicMock()
            mock_from_mp3.return_value = mock_audio_segment

            # record のモック
            mock_audio_data = MagicMock()
            mock_recognizer.record.return_value = mock_audio_data

            result = price_watch.captcha._recog_audio(audio_url)

        assert result == "hello world"
        mock_urlretrieve.assert_called_once()
        mock_from_mp3.assert_called_once()
        mock_audio_segment.export.assert_called_once()
        mock_recognizer.recognize_google.assert_called_once_with(mock_audio_data, language="en-US")
        # クリーンアップが呼ばれた（2回以上）
        assert mock_unlink.call_count >= 2

    def test_cleans_up_temp_files_on_error(self) -> None:
        """エラー時も一時ファイルをクリーンアップ"""
        audio_url = "https://example.com/audio.mp3"

        with (
            patch("urllib.request.urlretrieve", side_effect=Exception("Download failed")),
            patch("os.unlink") as mock_unlink,
        ):
            import pytest

            with pytest.raises(Exception, match="Download failed"):
                price_watch.captcha._recog_audio(audio_url)

        # finally ブロックでクリーンアップが呼ばれる（2回以上）
        assert mock_unlink.call_count >= 2


class TestResolveMp3:
    """resolve_mp3 関数のテスト"""

    def test_resolves_recaptcha(self) -> None:
        """reCAPTCHA を解決"""
        mock_driver = MagicMock()
        mock_wait = MagicMock()

        # audio 要素のモック
        mock_audio_elem = MagicMock()
        mock_audio_elem.get_attribute.return_value = "https://example.com/audio.mp3"

        # input 要素のモック
        mock_input_elem = MagicMock()

        def find_element(_by, xpath):
            if "audio-source" in xpath:
                return mock_audio_elem
            if "audio-response" in xpath:
                return mock_input_elem
            return MagicMock()

        mock_driver.find_element.side_effect = find_element

        with (
            patch("my_lib.selenium_util.click_xpath"),
            patch("price_watch.captcha._recog_audio", return_value="hello world"),
        ):
            price_watch.captcha.resolve_mp3(mock_driver, mock_wait)

        # wait.until が複数回呼ばれる
        assert mock_wait.until.call_count >= 3

        # 認識結果を入力
        mock_input_elem.send_keys.assert_called()

        # default_content に戻る
        mock_driver.switch_to.default_content.assert_called()

    def test_switches_to_iframe(self) -> None:
        """iframe に切り替え"""
        mock_driver = MagicMock()
        mock_wait = MagicMock()

        mock_audio_elem = MagicMock()
        mock_audio_elem.get_attribute.return_value = "https://example.com/audio.mp3"

        mock_input_elem = MagicMock()

        def find_element(_by, xpath):
            if "audio-source" in xpath:
                return mock_audio_elem
            if "audio-response" in xpath:
                return mock_input_elem
            return MagicMock()

        mock_driver.find_element.side_effect = find_element

        with (
            patch("my_lib.selenium_util.click_xpath"),
            patch("price_watch.captcha._recog_audio", return_value="test"),
        ):
            price_watch.captcha.resolve_mp3(mock_driver, mock_wait)

        # switch_to.default_content が呼ばれる（iframe からの復帰）
        assert mock_driver.switch_to.default_content.call_count == 2

    def test_enters_recognized_text_lowercase(self) -> None:
        """認識テキストを小文字で入力"""
        mock_driver = MagicMock()
        mock_wait = MagicMock()

        mock_audio_elem = MagicMock()
        mock_audio_elem.get_attribute.return_value = "https://example.com/audio.mp3"

        mock_input_elem = MagicMock()

        def find_element(_by, xpath):
            if "audio-source" in xpath:
                return mock_audio_elem
            if "audio-response" in xpath:
                return mock_input_elem
            return MagicMock()

        mock_driver.find_element.side_effect = find_element

        with (
            patch("my_lib.selenium_util.click_xpath"),
            patch("price_watch.captcha._recog_audio", return_value="HELLO WORLD"),
        ):
            price_watch.captcha.resolve_mp3(mock_driver, mock_wait)

        # 小文字に変換されて入力
        calls = mock_input_elem.send_keys.call_args_list
        assert calls[0][0][0] == "hello world"
