import { useState, useCallback, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchVapidPublicKey, subscribePush, unsubscribePush, fetchPushStatus } from "../services/apiService";

// Service Worker の登録パス
const SW_PATH = "/price/sw.js";

// クエリキー
export const pushQueryKeys = {
    vapidKey: ["pushVapidKey"] as const,
    status: (itemKey: string) => ["pushStatus", itemKey] as const,
};

// Base64 URL -> Uint8Array 変換
function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = window.atob(base64);
    const buffer = new ArrayBuffer(rawData.length);
    const outputArray = new Uint8Array(buffer);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

// ArrayBuffer -> Base64 URL 変換
function arrayBufferToBase64Url(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

export interface UsePushNotificationResult {
    // 状態
    isSupported: boolean;
    isLoading: boolean;
    isSubscribed: boolean;
    subscriptionCount: number;
    error: string | null;

    // 操作
    subscribe: () => Promise<void>;
    unsubscribe: () => Promise<void>;
    requestPermission: () => Promise<NotificationPermission>;

    // 権限状態
    permission: NotificationPermission;
}

export function usePushNotification(itemKey: string): UsePushNotificationResult {
    const queryClient = useQueryClient();

    // ブラウザのサポート状況
    const isSupported =
        typeof window !== "undefined" &&
        "serviceWorker" in navigator &&
        "PushManager" in window &&
        "Notification" in window;

    // 状態
    const [error, setError] = useState<string | null>(null);
    const [permission, setPermission] = useState<NotificationPermission>(
        isSupported ? Notification.permission : "default"
    );
    const [currentEndpoint, setCurrentEndpoint] = useState<string | null>(null);

    // Service Worker 登録と現在のサブスクリプションを取得
    useEffect(() => {
        if (!isSupported) return;

        const checkSubscription = async () => {
            try {
                const registration = await navigator.serviceWorker.getRegistration(SW_PATH);
                if (registration) {
                    const subscription = await registration.pushManager.getSubscription();
                    if (subscription) {
                        setCurrentEndpoint(subscription.endpoint);
                    }
                }
            } catch (e) {
                console.error("Failed to check subscription:", e);
            }
        };

        checkSubscription();
    }, [isSupported]);

    // VAPID 公開鍵を取得
    const vapidKeyQuery = useQuery({
        queryKey: pushQueryKeys.vapidKey,
        queryFn: fetchVapidPublicKey,
        enabled: isSupported,
        staleTime: Infinity, // 公開鍵は変わらないのでキャッシュを長く保持
    });

    // Push 通知の状態を取得
    const statusQuery = useQuery({
        queryKey: pushQueryKeys.status(itemKey),
        queryFn: () => fetchPushStatus(itemKey, currentEndpoint || undefined),
        enabled: isSupported && !!itemKey,
    });

    // サブスクライブ mutation
    const subscribeMutation = useMutation({
        mutationFn: async () => {
            if (!vapidKeyQuery.data) {
                throw new Error("VAPID public key not available");
            }

            // Service Worker を登録
            const registration = await navigator.serviceWorker.register(SW_PATH, {
                scope: "/price/",
            });

            // Service Worker がアクティブになるまで待機
            await navigator.serviceWorker.ready;

            // 既存のサブスクリプションを解除
            const existingSub = await registration.pushManager.getSubscription();
            if (existingSub) {
                await existingSub.unsubscribe();
            }

            // 新しいサブスクリプションを作成
            const subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(vapidKeyQuery.data.public_key),
            });

            // サーバーに登録
            const p256dh = subscription.getKey("p256dh");
            const auth = subscription.getKey("auth");

            if (!p256dh || !auth) {
                throw new Error("Failed to get subscription keys");
            }

            await subscribePush({
                item_key: itemKey,
                endpoint: subscription.endpoint,
                keys: {
                    p256dh: arrayBufferToBase64Url(p256dh),
                    auth: arrayBufferToBase64Url(auth),
                },
            });

            setCurrentEndpoint(subscription.endpoint);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: pushQueryKeys.status(itemKey) });
            setError(null);
        },
        onError: (e: Error) => {
            setError(e.message);
        },
    });

    // アンサブスクライブ mutation
    const unsubscribeMutation = useMutation({
        mutationFn: async () => {
            if (!currentEndpoint) {
                throw new Error("No active subscription");
            }

            // サーバーから削除
            await unsubscribePush(itemKey, currentEndpoint);

            // ブラウザのサブスクリプションも解除（他のアイテムには影響しない）
            // ※ここでは解除しない。他のアイテムでも同じサブスクリプションを使用している可能性があるため
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: pushQueryKeys.status(itemKey) });
            setError(null);
        },
        onError: (e: Error) => {
            setError(e.message);
        },
    });

    // 権限をリクエスト
    const requestPermission = useCallback(async (): Promise<NotificationPermission> => {
        if (!isSupported) {
            return "denied";
        }
        const result = await Notification.requestPermission();
        setPermission(result);
        return result;
    }, [isSupported]);

    // サブスクライブ
    const subscribe = useCallback(async () => {
        setError(null);

        // 権限を確認
        if (permission !== "granted") {
            const result = await requestPermission();
            if (result !== "granted") {
                setError("通知の許可が必要です");
                return;
            }
        }

        await subscribeMutation.mutateAsync();
    }, [permission, requestPermission, subscribeMutation]);

    // アンサブスクライブ
    const unsubscribe = useCallback(async () => {
        setError(null);
        await unsubscribeMutation.mutateAsync();
    }, [unsubscribeMutation]);

    return {
        isSupported,
        isLoading:
            vapidKeyQuery.isLoading ||
            statusQuery.isLoading ||
            subscribeMutation.isPending ||
            unsubscribeMutation.isPending,
        isSubscribed: statusQuery.data?.subscribed ?? false,
        subscriptionCount: statusQuery.data?.subscription_count ?? 0,
        error,
        subscribe,
        unsubscribe,
        requestPermission,
        permission,
    };
}
