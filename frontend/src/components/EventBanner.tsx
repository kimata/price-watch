import { useState, useEffect, useCallback } from "react";
import { fetchEvents } from "../services/apiService";
import type { Event, EventType } from "../types";

interface EventBannerProps {
    refreshInterval?: number; // ms
}

const EVENT_CONFIG: Record<
    EventType,
    {
        emoji: string;
        icon: string;
        bgColor: string;
        borderColor: string;
        textColor: string;
        label: string;
    }
> = {
    back_in_stock: {
        emoji: "📦",
        icon: "cube",
        bgColor: "bg-emerald-50",
        borderColor: "border-emerald-300",
        textColor: "text-emerald-700",
        label: "在庫復活",
    },
    crawl_failure: {
        emoji: "⚠️",
        icon: "exclamation-triangle",
        bgColor: "bg-amber-50",
        borderColor: "border-amber-300",
        textColor: "text-amber-700",
        label: "取得失敗",
    },
    lowest_price: {
        emoji: "🔥",
        icon: "fire",
        bgColor: "bg-rose-50",
        borderColor: "border-rose-300",
        textColor: "text-rose-700",
        label: "最安値更新",
    },
    price_drop: {
        emoji: "📉",
        icon: "trending-down",
        bgColor: "bg-sky-50",
        borderColor: "border-sky-300",
        textColor: "text-sky-700",
        label: "値下げ",
    },
};

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
        return (
            <div className="mb-6">
                <h2 className="text-lg font-semibold text-gray-700 mb-3 flex items-center gap-2">
                    <span className="text-xl">🔔</span>
                    最新イベント
                </h2>
                <div className="p-6 bg-red-50 border border-red-200 rounded-xl text-center">
                    <span className="text-2xl mb-2 block">❌</span>
                    <p className="text-red-600 text-sm">{error}</p>
                </div>
            </div>
        );
    }

    if (events.length === 0) {
        return (
            <div className="mb-6">
                <h2 className="text-lg font-semibold text-gray-700 mb-3 flex items-center gap-2">
                    <span className="text-xl">🔔</span>
                    最新イベント
                </h2>
                <div className="p-6 bg-gray-50 border border-gray-200 rounded-xl text-center">
                    <span className="text-2xl mb-2 block">📭</span>
                    <p className="text-gray-500 text-sm">まだイベントはありません</p>
                    <p className="text-gray-400 text-xs mt-1">価格変動や在庫復活があると、ここに表示されます</p>
                </div>
            </div>
        );
    }

    return (
        <div className="mb-6">
            <h2 className="text-lg font-semibold text-gray-700 mb-3 flex items-center gap-2">
                <span className="text-xl">🔔</span>
                最新イベント
                <span className="text-sm font-normal text-gray-400">({events.length}件)</span>
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
                            className={`flex-shrink-0 w-80 p-4 rounded-xl border-2 ${config.bgColor} ${config.borderColor} hover:shadow-lg hover:scale-[1.02] transition-all duration-200 cursor-pointer`}
                        >
                            <div className="flex items-start gap-3">
                                {/* サムネイル */}
                                <div className="relative flex-shrink-0">
                                    {event.thumb_url ? (
                                        <img
                                            src={event.thumb_url}
                                            alt={event.item_name}
                                            className="w-14 h-14 object-cover rounded-lg"
                                        />
                                    ) : (
                                        <div className="w-14 h-14 bg-gray-200 rounded-lg flex items-center justify-center">
                                            <svg
                                                className="w-7 h-7 text-gray-400"
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
                                    {/* 絵文字バッジ */}
                                    <span className="absolute -top-1 -right-1 text-lg drop-shadow-sm">
                                        {config.emoji}
                                    </span>
                                </div>

                                {/* コンテンツ */}
                                <div className="flex-1 min-w-0">
                                    {/* タイトル行 */}
                                    <div className="flex items-center gap-2 mb-1">
                                        <span
                                            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${config.bgColor} ${config.textColor} border ${config.borderColor}`}
                                        >
                                            {config.label}
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
                                                    <span className="text-gray-400">→</span>
                                                </>
                                            )}
                                            <span className={`text-base font-bold ${config.textColor}`}>
                                                {formatPrice(event.price)}
                                            </span>
                                            {event.old_price !== null && event.old_price > event.price && (
                                                <span className="text-xs text-rose-500 font-medium">
                                                    -{((event.old_price - event.price) / event.old_price * 100).toFixed(0)}%
                                                </span>
                                            )}
                                        </div>
                                    )}

                                    {/* ストア名 */}
                                    <p className="text-xs text-gray-500 mt-1 flex items-center gap-1">
                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                                        </svg>
                                        {event.store}
                                    </p>
                                </div>
                            </div>
                        </a>
                    );
                })}
            </div>
        </div>
    );
}
