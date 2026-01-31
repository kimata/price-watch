#!/usr/bin/env python3
# ruff: noqa: S101
"""
affiliate.py のユニットテスト
"""

import price_watch.affiliate
from price_watch.target import CheckMethod


class TestAppendAffiliateId:
    """append_affiliate_id のテスト"""

    def test_mercari_url(self):
        """メルカリURLにアフィリエイトIDを付与"""
        url = "https://jp.mercari.com/item/m12345678901"
        result = price_watch.affiliate.append_affiliate_id(url, "my_affiliate", CheckMethod.MERCARI_SEARCH)
        assert result == "https://jp.mercari.com/item/m12345678901?afid=my_affiliate"

    def test_rakuma_url(self):
        """ラクマURLにアフィリエイトIDを付与"""
        url = "https://fril.jp/item/12345678"
        result = price_watch.affiliate.append_affiliate_id(url, "my_affiliate", CheckMethod.RAKUMA_SEARCH)
        assert result == "https://fril.jp/item/12345678?afid=my_affiliate"

    def test_paypay_url(self):
        """PayPayフリマURLにアフィリエイトIDを付与"""
        url = "https://paypayfleamarket.yahoo.co.jp/item/z12345678"
        result = price_watch.affiliate.append_affiliate_id(url, "my_affiliate", CheckMethod.PAYPAY_SEARCH)
        assert result == "https://paypayfleamarket.yahoo.co.jp/item/z12345678?afid=my_affiliate"

    def test_amazon_url(self):
        """AmazonURLにアフィリエイトタグを付与"""
        url = "https://www.amazon.co.jp/dp/B0123456789"
        result = price_watch.affiliate.append_affiliate_id(url, "my-tag-22", CheckMethod.AMAZON_PAAPI)
        assert result == "https://www.amazon.co.jp/dp/B0123456789?tag=my-tag-22"

    def test_url_with_existing_query(self):
        """既存のクエリストリングがあるURLに追加"""
        url = "https://jp.mercari.com/item/m12345678901?ref=search"
        result = price_watch.affiliate.append_affiliate_id(url, "my_affiliate", CheckMethod.MERCARI_SEARCH)
        assert result == "https://jp.mercari.com/item/m12345678901?ref=search&afid=my_affiliate"

    def test_existing_afid_not_overwritten(self):
        """既存のafidパラメータは上書きしない"""
        url = "https://jp.mercari.com/item/m12345678901?afid=existing"
        result = price_watch.affiliate.append_affiliate_id(url, "my_affiliate", CheckMethod.MERCARI_SEARCH)
        assert result == "https://jp.mercari.com/item/m12345678901?afid=existing"

    def test_existing_tag_not_overwritten(self):
        """既存のtagパラメータは上書きしない"""
        url = "https://www.amazon.co.jp/dp/B0123456789?tag=existing-22"
        result = price_watch.affiliate.append_affiliate_id(url, "my-tag-22", CheckMethod.AMAZON_PAAPI)
        assert result == "https://www.amazon.co.jp/dp/B0123456789?tag=existing-22"

    def test_none_affiliate_id(self):
        """affiliate_idがNoneの場合はURLを変更しない"""
        url = "https://jp.mercari.com/item/m12345678901"
        result = price_watch.affiliate.append_affiliate_id(url, None, CheckMethod.MERCARI_SEARCH)
        assert result == "https://jp.mercari.com/item/m12345678901"

    def test_empty_url(self):
        """空文字列のURLの場合はそのまま返す"""
        result = price_watch.affiliate.append_affiliate_id("", "my_affiliate", CheckMethod.MERCARI_SEARCH)
        assert result == ""

    def test_scrape_method_returns_unchanged(self):
        """SCRAPE メソッドの場合はURLを変更しない"""
        url = "https://example.com/product/123"
        result = price_watch.affiliate.append_affiliate_id(url, "my_affiliate", CheckMethod.SCRAPE)
        assert result == "https://example.com/product/123"

    def test_yahoo_method_returns_unchanged(self):
        """YAHOO_SEARCH メソッドの場合はURLを変更しない"""
        url = "https://shopping.yahoo.co.jp/product/123"
        result = price_watch.affiliate.append_affiliate_id(url, "my_affiliate", CheckMethod.YAHOO_SEARCH)
        assert result == "https://shopping.yahoo.co.jp/product/123"

    def test_url_with_fragment(self):
        """フラグメントを含むURLでも正しく処理"""
        url = "https://www.amazon.co.jp/dp/B0123456789#details"
        result = price_watch.affiliate.append_affiliate_id(url, "my-tag-22", CheckMethod.AMAZON_PAAPI)
        assert result == "https://www.amazon.co.jp/dp/B0123456789?tag=my-tag-22#details"
