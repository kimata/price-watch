import React, { useState, useEffect, useCallback } from "react";
import { fetchEvents } from "../services/apiService";
import type { Event, EventType } from "../types";

interface EventBannerProps {
    refreshInterval?: number; // ms
}

const EVENT_CONFIG: Record<
    EventType,
    { icon: string; bgColor: string; borderColor: string; textColor: string }
> = {
    back_in_stock: {
        icon: "cube",
        bgColor: "bg-green-50",
        borderColor: "border-green-200",
        textColor: "text-green-700",
    },
    crawl_failure: {
        icon: "exclamation-triangle",
        bgColor: "bg-yellow-50",
        borderColor: "border-yellow-200",
        textColor: "text-yellow-700",
    },
    lowest_price: {
        icon: "fire",
        bgColor: "bg-red-50",
        borderColor: "border-red-200",
        textColor: "text-red-700",
    },
    price_drop: {
        icon: "trending-down",
        bgColor: "bg-blue-50",
        borderColor: "border-blue-200",
        textColor: "text-blue-700",
    },
};

function getEventIcon(eventType: EventType): React.ReactElement {
    const config = EVENT_CONFIG[eventType];

    switch (config.icon) {
        case "cube":
            return (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
                    />
                </svg>
            );
        case "exclamation-triangle":
            return (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                    />
                </svg>
            );
        case "fire":
            return (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.343A7.975 7.975 0 0120 13a7.975 7.975 0 01-2.343 5.657z"
                    />
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9.879 16.121A3 3 0 1012.015 11L11 14H9c0 .768.293 1.536.879 2.121z"
                    />
                </svg>
            );
        case "trending-down":
            return (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6"
                    />
                </svg>
            );
        default:
            return (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
                    />
                </svg>
            );
    }
}

function formatTimeAgo(dateStr: string): string {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMinutes = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffMinutes < 1) return "たった今";
    if (diffMinutes < 60) return `${diffMinutes}分前`;
    if (diffHours < 24) return `${diffHours}時間前`;
    if (diffDays < 7) return `${diffDays}日前`;

    return date.toLocaleDateString("ja-JP", {
        month: "numeric",
        day: "numeric",
    });
}

function formatPrice(price: number | null): string {
    if (price === null) return "-";
    return price.toLocaleString("ja-JP") + "円";
}

export default function EventBanner({ refreshInterval = 60000 }: EventBannerProps) {
    const [events, setEvents] = useState<Event[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const loadEvents = useCallback(async () => {
        try {
            const response = await fetchEvents(10);
            setEvents(response.events);
            setError(null);
        } catch (err) {
            console.error("Failed to load events:", err);
            setError("イベントの取得に失敗しました");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadEvents();

        // 定期的に更新
        const intervalId = setInterval(loadEvents, refreshInterval);
        return () => clearInterval(intervalId);
    }, [loadEvents, refreshInterval]);

    if (loading) {
        return (
            <div className="mb-6 p-4 bg-gray-50 rounded-lg animate-pulse">
                <div className="h-6 bg-gray-200 rounded w-32 mb-3"></div>
                <div className="flex space-x-4 overflow-hidden">
                    {[1, 2, 3].map((i) => (
                        <div key={i} className="flex-shrink-0 w-72 h-24 bg-gray-200 rounded-lg"></div>
                    ))}
                </div>
            </div>
        );
    }

    if (error) {
        return null; // エラー時は非表示
    }

    if (events.length === 0) {
        return null; // イベントがない場合は非表示
    }

    return (
        <div className="mb-6">
            <h2 className="text-lg font-semibold text-gray-700 mb-3 flex items-center gap-2">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
                    />
                </svg>
                最新イベント
            </h2>
            <div className="flex space-x-4 overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-gray-100">
                {events.map((event) => {
                    const config = EVENT_CONFIG[event.event_type] || EVENT_CONFIG.price_drop;

                    return (
                        <a
                            key={event.id}
                            href={event.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className={`flex-shrink-0 w-80 p-4 rounded-lg border-2 ${config.bgColor} ${config.borderColor} hover:shadow-md transition-shadow cursor-pointer`}
                        >
                            <div className="flex items-start gap-3">
                                {/* サムネイル */}
                                {event.thumb_url ? (
                                    <img
                                        src={event.thumb_url}
                                        alt={event.item_name}
                                        className="w-12 h-12 object-cover rounded flex-shrink-0"
                                    />
                                ) : (
                                    <div className="w-12 h-12 bg-gray-200 rounded flex-shrink-0 flex items-center justify-center">
                                        <svg
                                            className="w-6 h-6 text-gray-400"
                                            fill="none"
                                            stroke="currentColor"
                                            viewBox="0 0 24 24"
                                        >
                                            <path
                                                strokeLinecap="round"
                                                strokeLinejoin="round"
                                                strokeWidth={2}
                                                d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                                            />
                                        </svg>
                                    </div>
                                )}

                                {/* コンテンツ */}
                                <div className="flex-1 min-w-0">
                                    {/* タイトル行 */}
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className={config.textColor}>
                                            {getEventIcon(event.event_type)}
                                        </span>
                                        <span className={`text-sm font-medium ${config.textColor}`}>
                                            {event.title}
                                        </span>
                                        <span className="text-xs text-gray-400 ml-auto flex-shrink-0">
                                            {formatTimeAgo(event.created_at)}
                                        </span>
                                    </div>

                                    {/* 商品名 */}
                                    <p className="text-sm text-gray-800 font-medium truncate">
                                        {event.item_name}
                                    </p>

                                    {/* 価格情報 */}
                                    {event.price !== null && (
                                        <div className="flex items-center gap-2 mt-1">
                                            {event.old_price !== null && (
                                                <>
                                                    <span className="text-xs text-gray-400 line-through">
                                                        {formatPrice(event.old_price)}
                                                    </span>
                                                    <span className="text-xs text-gray-400">→</span>
                                                </>
                                            )}
                                            <span className={`text-sm font-bold ${config.textColor}`}>
                                                {formatPrice(event.price)}
                                            </span>
                                        </div>
                                    )}

                                    {/* ストア名 */}
                                    <p className="text-xs text-gray-400 mt-1">{event.store}</p>
                                </div>
                            </div>
                        </a>
                    );
                })}
            </div>
        </div>
    );
}
