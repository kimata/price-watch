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
    logging.info("process action: {name}".format(name=item["name"]))

    for action in action_list:
        logging.debug("action: {action}.".format(action=action["type"]))
        if action["type"] == "input":
            if not xpath_exists(driver, resolve_template(action["xpath"], item)):
                logging.debug("Element not found. Interrupted.")
                return
            driver.find_element(By.XPATH, resolve_template(action["xpath"], item)).send_keys(
                resolve_template(action["value"], item)
            )
        elif action["type"] == "click":
            if not xpath_exists(driver, resolve_template(action["xpath"], item)):
                logging.debug("Element not found. Interrupted.")
                return
            driver.find_element(By.XPATH, resolve_template(action["xpath"], item)).click()
        elif action["type"] == "recaptcha":
            captcha.resolve_mp3(config, driver, wait)
        elif action["type"] == "captcha":
            input_xpath = '//input[@id="captchacharacters"]'
            if not xpath_exists(driver, input_xpath):
                logging.debug("Element not found.")
                continue
            domain = urllib.parse.urlparse(driver.current_url).netloc

            logging.warning("Resolve captche is needed at {domain}.".format(domain=domain))

            dump_page(driver, int(random.random() * 100))
            code = input("{domain} captcha: ".format(domain=domain))

            driver.find_element(By.XPATH, input_xpath).send_keys(code)
            driver.find_element(By.XPATH, '//button[@type="submit"]').click()
        elif action["type"] == "sixdigit":
            # NOTE: これは今のところ Ubiquiti Store USA 専用
            digit_code = input(
                "{domain} app code: ".format(domain=urllib.parse.urlparse(driver.current_url).netloc)
            )
            for i, code in enumerate(list(digit_code)):
                driver.find_element(By.XPATH, '//input[@data-id="' + str(i) + '"]').send_keys(code)
        time.sleep(4)


def process_preload(config, driver, wait, item, loop):
    logging.info("process preload: {name}".format(name=item["name"]))

    if "preload" not in item:
        return

    if (loop % item["preload"]["every"]) != 0:
        logging.info("skip preload. (loop={loop})".format(loop=loop))
        return

    driver.get(item["preload"]["url"])
    time.sleep(2)

    process_action(config, driver, wait, item, item["preload"]["action"], "preload action")


def check_impl(config, driver, item, loop):
    wait = WebDriverWait(driver, TIMEOUT_SEC)

    process_preload(config, driver, wait, item, loop)

    logging.info("fetch: {url}".format(url=item["url"]))

    driver.get(item["url"])
    time.sleep(2)

    if "action" in item:
        process_action(config, driver, wait, item, item["action"])

    logging.info("parse: {name}".format(name=item["name"]))

    if not xpath_exists(driver, item["price_xpath"]):
        logging.warning("{name}: price not found.".format(name=item["name"]))
        item["stock"] = 0
        dump_page(driver, int(random.random() * 100))
        return False

    if "unavailable_xpath" in item:
        if len(driver.find_elements(By.XPATH, item["unavailable_xpath"])) != 0:
            item["stock"] = 0
        else:
            item["stock"] = 1
    else:
        item["stock"] = 1

    price_text = driver.find_element(By.XPATH, item["price_xpath"]).text
    try:
        m = re.match(r".*?(\d{1,3}(?:,\d{3})*)", price_text)
        item["price"] = int(m.group(1).replace(",", ""))
    except:
        if item["stock"] == 0:
            # NOTE: 在庫がない場合は，価格が取得できなくてもエラーにしない
            pass
        else:
            logging.debug(f"unable to parse price: '{price_text}'")
            raise

    if "thumb_url" not in item:
        if ("thumb_img_xpath" in item) and xpath_exists(driver, item["thumb_img_xpath"]):
            item["thumb_url"] = urllib.parse.urljoin(
                driver.current_url,
                driver.find_element(By.XPATH, item["thumb_img_xpath"]).get_attribute("src"),
            )
    elif ("thumb_block_xpath" in item) and xpath_exists(driver, item["thumb_block_xpath"]):
        style_text = driver.find_element(By.XPATH, item["thumb_block_xpath"]).get_attribute("style")
        m = re.match(
            r"background-image: url\([\"'](.*)[\"']\)",
            style_text,
        )
        thumb_url = m.group(1)
        if not re.compile(r"^\.\.").search(thumb_url):
            thumb_url = "/" + thumb_url

        item["thumb_url"] = urllib.parse.urljoin(driver.current_url, thumb_url)

    return item


def check(config, driver, item, loop):
    try:
        logging.warning("Check {name}".format(name=item["name"]))

        return check_impl(config, driver, item, loop)
    except:
        logging.error("URL: {url}".format(url=driver.current_url))
        logging.error(traceback.format_exc())
        dump_page(driver, int(random.random() * 100))
        clean_dump()
        raise
