#!/usr/bin/env python3
"""CAPTCHA 解決処理."""

from __future__ import annotations

import os
import tempfile
import time
import urllib.request
from typing import TYPE_CHECKING

import my_lib.selenium_util
import pydub
import selenium.webdriver.common.by
import selenium.webdriver.common.keys
import selenium.webdriver.support.expected_conditions
import selenium.webdriver.support.wait
import speech_recognition

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver


def _recog_audio(audio_url: str) -> str:
    """音声を認識してテキストに変換."""
    mp3_file = tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".mp3")
    wav_file = tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".wav")

    try:
        urllib.request.urlretrieve(audio_url, mp3_file.name)

        pydub.AudioSegment.from_mp3(mp3_file.name).export(wav_file.name, format="wav")

        recognizer = speech_recognition.Recognizer()
        recaptcha_audio = speech_recognition.AudioFile(wav_file.name)
        with recaptcha_audio as source:
            audio = recognizer.record(source)

        return recognizer.recognize_google(audio, language="en-US")
    finally:
        os.unlink(mp3_file.name)
        os.unlink(wav_file.name)


def resolve_mp3(
    driver: WebDriver,
    wait: selenium.webdriver.support.wait.WebDriverWait,  # type: ignore[type-arg]
) -> None:
    """reCAPTCHA を音声認識で解決."""
    By = selenium.webdriver.common.by.By
    EC = selenium.webdriver.support.expected_conditions
    Keys = selenium.webdriver.common.keys.Keys

    wait.until(EC.frame_to_be_available_and_switch_to_it((By.XPATH, '//iframe[@title="reCAPTCHA"]')))
    my_lib.selenium_util.click_xpath(
        driver,
        '//span[contains(@class, "recaptcha-checkbox")]',
    )
    driver.switch_to.default_content()
    wait.until(
        EC.frame_to_be_available_and_switch_to_it(
            (By.XPATH, '//iframe[contains(@title, "reCAPTCHA による確認")]')
        )
    )
    wait.until(EC.element_to_be_clickable((By.XPATH, '//div[@id="rc-imageselect-target"]')))
    my_lib.selenium_util.click_xpath(driver, '//button[contains(@title, "確認用の文字を音声")]')
    time.sleep(0.5)

    audio_url = driver.find_element(By.XPATH, '//audio[@id="audio-source"]').get_attribute("src")

    text = _recog_audio(audio_url)

    input_elem = driver.find_element(By.XPATH, '//input[@id="audio-response"]')
    input_elem.send_keys(text.lower())
    input_elem.send_keys(Keys.ENTER)

    driver.switch_to.default_content()
