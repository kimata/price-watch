#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import string
import urllib
import pathlib
import os
import random
import time
import re
import traceback

from selenium.webdriver.support.wait import WebDriverWait

from selenium.webdriver.common.by import By
from selenium_util import xpath_exists, dump_page, clean_dump

import captcha

TIMEOUT_SEC = 4
DATA_PATH = pathlib.Path(os.path.dirname(__file__)).parent / "data"
DUMP_PATH = str(DATA_PATH / "debug")


def resolve_template(template, item):
    tmpl = string.Template(template)
    return tmpl.safe_substitute(item_name=item["name"])


def process_action(config, driver, wait, item, action_list, name="action"):
    logging.info("process {name}.".format(name=name))

    for action in action_list:
        logging.info("action: {action}.".format(action=action["type"]))
        if action["type"] == "input":
            if not xpath_exists(driver, resolve_template(action["xpath"], item)):
                logging.info("Element not found. Interrupted.")
                return
            driver.find_element(
                By.XPATH, resolve_template(action["xpath"], item)
            ).send_keys(resolve_template(action["value"], item))
        elif action["type"] == "click":
            if not xpath_exists(driver, resolve_template(action["xpath"], item)):
                logging.info("Element not found. Interrupted.")
                return
            driver.find_element(
                By.XPATH, resolve_template(action["xpath"], item)
            ).click()
        elif action["type"] == "recaptcha":
            captcha.resolve_mp3(config, driver, wait)
        elif action["type"] == "captcha":
            input_xpath = '//input[@id="captchacharacters"]'
            if not xpath_exists(driver, input_xpath):
                logging.info("Element not found.")
                continue
            domain = urllib.parse.urlparse(driver.current_url).netloc

            logging.warning(
                "Resolve captche is needed at {domain}.".format(domain=domain)
            )

            dump_page(driver, int(random.random() * 100))
            code = input("{domain} captcha: ".format(domain=domain))

            driver.find_element(By.XPATH, input_xpath).send_keys(code)
            driver.find_element(By.XPATH, '//button[@type="submit"]').click()
        elif action["type"] == "sixdigit":
            # NOTE: これは今のところ Ubiquiti Store USA 専用
            digit_code = input(
                "{domain} app code: ".format(
                    domain=urllib.parse.urlparse(driver.current_url).netloc
                )
            )
            for i, code in enumerate(list(digit_code)):
                driver.find_element(
                    By.XPATH, '//input[@data-id="' + str(i) + '"]'
                ).send_keys(code)
        time.sleep(4)


def process_preload(config, driver, wait, item, loop):
    if "preload" not in item:
        return

    if (loop % item["preload"]["every"]) != 0:
        logging.info("skip preload. (loop={loop})".format(loop=loop))
        return

    driver.get(item["preload"]["url"])
    time.sleep(2)

    process_action(
        config, driver, wait, item, item["preload"]["action"], "preload action"
    )


def check_impl(config, driver, item, loop):
    wait = WebDriverWait(driver, TIMEOUT_SEC)

    process_preload(config, driver, wait, item, loop)

    driver.get(item["url"])
    time.sleep(2)

    if "action" in item:
        process_action(config, driver, wait, item, item["action"])

    if not xpath_exists(driver, item["price_xpath"]):
        logging.warning("{name}: price not found.".format(name=item["name"]))
        dump_page(driver, int(random.random() * 100))
        return False

    price_text = driver.find_element(By.XPATH, item["price_xpath"]).text

    m = re.match(r".*?(\d{1,3}(?:,\d{3})*)", price_text)
    item["price"] = int(m.group(1).replace(",", ""))

    if "unavailable_xpath" in item:
        if len(driver.find_elements(By.XPATH, item["unavailable_xpath"])) != 0:
            item["stock"] = 0
        else:
            item["stock"] = 1
    else:
        item["stock"] = 1

    if (
        ("thumb_url" not in item)
        and ("thumb_xpath" in item)
        and xpath_exists(driver, item["thumb_xpath"])
    ):
        item["thumb_url"] = driver.find_element(
            By.XPATH, item["thumb_xpath"]
        ).get_attribute("src")

    return item


def check(config, driver, item, loop):
    try:
        return check_impl(config, driver, item, loop)
    except:
        logging.error("URL: {url}".format(url=driver.current_url))
        logging.error(traceback.format_exc())
        dump_page(driver, int(random.random() * 100))
        clean_dump()
        raise
