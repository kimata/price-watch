#!/usr/bin/env python3
"""Web Push 通知サービス.

Web Push API を使用してブラウザ通知を送信します。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pywebpush import WebPushException, webpush

if TYPE_CHECKING:
    from price_watch.config import WebPushConfig
    from price_watch.managers.history import HistoryManager

# Web Push 通知対象のイベントタイプ（価格系のみ）
NOTIFIABLE_EVENT_TYPES = frozenset({"price_drop", "lowest_price", "back_in_stock"})


@dataclass(frozen=True)
class PushNotificationPayload:
    """Push 通知ペイロード."""

    title: str
    body: str
    url: str | None = None
    icon: str | None = None
    tag: str | None = None


@dataclass
class WebPushService:
    """Web Push 通知サービス.

    VAPID 認証を使用して Web Push 通知を送信します。
    """

    config: WebPushConfig
    history_manager: HistoryManager

    def send_notification(
        self,
        item_key: str,
        title: str,
        body: str,
        *,
        url: str | None = None,
        icon: str | None = None,
        tag: str | None = None,
    ) -> int:
        """指定アイテムの全サブスクライバーに通知を送信.

        Args:
            item_key: 監視対象アイテムキー
            title: 通知タイトル
            body: 通知本文
            url: クリック時に開く URL
            icon: 通知アイコン URL
            tag: 通知タグ（同一タグの通知は上書き）

        Returns:
            送信成功した数
        """
        subscriptions = self.history_manager.push.get_subscriptions(item_key)
        if not subscriptions:
            return 0

        payload = PushNotificationPayload(
            title=title,
            body=body,
            url=url,
            icon=icon,
            tag=tag or item_key,
        )

        success_count = 0
        expired_endpoints: list[str] = []

        for sub in subscriptions:
            try:
                self._send_to_endpoint(
                    endpoint=sub.endpoint,
                    p256dh=sub.p256dh,
                    auth=sub.auth,
                    payload=payload,
                )
                success_count += 1
            except WebPushException as e:
                if e.response is not None and e.response.status_code == 410:
                    # サブスクリプション失効
                    logging.info("Push subscription expired: %s", sub.endpoint[:50])
                    expired_endpoints.append(sub.endpoint)
                else:
                    logging.warning(
                        "Failed to send push notification: %s (status=%s)",
                        e,
                        e.response.status_code if e.response else "N/A",
                    )
            except Exception:
                logging.exception("Unexpected error sending push notification")

        # 失効したサブスクリプションを削除
        for endpoint in expired_endpoints:
            self.history_manager.push.delete_by_endpoint(endpoint)

        logging.info(
            "Push notifications sent for %s: %d/%d succeeded",
            item_key,
            success_count,
            len(subscriptions),
        )
        return success_count

    def _send_to_endpoint(
        self,
        endpoint: str,
        p256dh: str,
        auth: str,
        payload: PushNotificationPayload,
    ) -> None:
        """単一エンドポイントに通知を送信.

        Args:
            endpoint: Push Service エンドポイント
            p256dh: 公開鍵
            auth: 認証シークレット
            payload: 通知ペイロード

        Raises:
            WebPushException: 送信失敗時
        """
        subscription_info = {
            "endpoint": endpoint,
            "keys": {
                "p256dh": p256dh,
                "auth": auth,
            },
        }

        data = {
            "title": payload.title,
            "body": payload.body,
        }
        if payload.url:
            data["url"] = payload.url
        if payload.icon:
            data["icon"] = payload.icon
        if payload.tag:
            data["tag"] = payload.tag

        webpush(
            subscription_info=subscription_info,
            data=json.dumps(data),
            vapid_private_key=self.config.vapid_private_key,
            vapid_claims={"sub": self.config.vapid_claims_email},
        )

    def subscribe(
        self,
        item_key: str,
        endpoint: str,
        p256dh: str,
        auth: str,
    ) -> int:
        """サブスクリプションを登録.

        Args:
            item_key: 監視対象アイテムキー
            endpoint: Push Service エンドポイント
            p256dh: 公開鍵
            auth: 認証シークレット

        Returns:
            サブスクリプション ID
        """
        return self.history_manager.push.subscribe(
            item_key=item_key,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
        )

    def unsubscribe(self, item_key: str, endpoint: str) -> bool:
        """サブスクリプションを解除.

        Args:
            item_key: 監視対象アイテムキー
            endpoint: Push Service エンドポイント

        Returns:
            解除された場合 True
        """
        return self.history_manager.push.unsubscribe(item_key, endpoint)

    def is_subscribed(self, item_key: str, endpoint: str) -> bool:
        """サブスクリプションが存在するか確認.

        Args:
            item_key: 監視対象アイテムキー
            endpoint: Push Service エンドポイント

        Returns:
            存在する場合 True
        """
        return self.history_manager.push.is_subscribed(item_key, endpoint)

    @property
    def vapid_public_key(self) -> str:
        """VAPID 公開鍵を取得."""
        return self.config.vapid_public_key


def is_notifiable_event(event_type: str) -> bool:
    """Web Push 通知対象のイベントタイプか判定.

    Args:
        event_type: イベントタイプ

    Returns:
        通知対象の場合 True
    """
    return event_type in NOTIFIABLE_EVENT_TYPES
