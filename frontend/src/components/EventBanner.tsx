import { useState, useEffect, useCallback } from "react";
import { BellIcon } from "@heroicons/react/24/outline";
import {
    CubeIcon,
    ExclamationTriangleIcon,
    FireIcon,
    ArrowTrendingDownIcon,
} from "@heroicons/react/24/solid";
import { fetchEvents } from "../services/apiService";
import type { Event, EventType } from "../types";

interface EventBannerProps {
    refreshInterval?: number; // ms
}

const EVENT_CONFIG: Record<
    EventType,
    {
        Icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
        bgColor: string;
        borderColor: string;
        textColor: string;
        iconColor: string;
        label: string;
    }
> = {
    back_in_stock: {
        Icon: CubeIcon,
        bgColor: "bg-emerald-50",
        borderColor: "border-emerald-200",
        textColor: "text-emerald-700",
        iconColor: "text-emerald-500",
        label: "在庫復活",
    },
    crawl_failure: {
        Icon: ExclamationTriangleIcon,
        bgColor: "bg-amber-50",
        borderColor: "border-amber-200",
        textColor: "text-amber-700",
        iconColor: "text-amber-500",
        label: "取得失敗",
    },
    data_retrieval_failure: {
        Icon: ExclamationTriangleIcon,
        bgColor: "bg-red-50",
        borderColor: "border-red-200",
        textColor: "text-red-700",
        iconColor: "text-red-500",
        label: "情報取得エラー",
    },
    lowest_price: {
        Icon: FireIcon,
        bgColor: "bg-green-50",
        borderColor: "border-green-200",
        textColor: "text-green-700",
        iconColor: "text-green-500",
        label: "最安値更新",
    },
    price_drop: {
        Icon: ArrowTrendingDownIcon,
        bgColor: "bg-sky-50",
        borderColor: "border-sky-200",
        textColor: "text-sky-700",
        iconColor: "text-sky-500",
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
    const [showAll, setShowAll] = useState(false);

    // showAll が false の場合、crawl_failure を除外
    const filteredEvents = showAll
        ? events
        : events.filter((e) => e.event_type !== "crawl_failure");

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
            <div className="mt-10 mb-6 p-4 bg-gray-50 rounded-lg animate-pulse">
                <div className="h-6 bg-gray-200 rounded w-32 mb-3"></div>
                <div className="space-y-2">
                    {[1, 2, 3].map((i) => (
                        <div key={i} className="h-12 bg-gray-200 rounded"></div>
                    ))}
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="mt-10 mb-6">
                <h2 className="text-lg font-semibold text-gray-700 mb-3 flex items-center gap-2">
                    <BellIcon className="w-5 h-5 text-gray-500" />
                    最新イベント
                </h2>
                <div className="p-6 bg-red-50 border border-red-200 rounded-xl text-center">
                    <ExclamationTriangleIcon className="w-8 h-8 text-red-400 mx-auto mb-2" />
                    <p className="text-red-600 text-sm">{error}</p>
                </div>
            </div>
        );
    }

    if (filteredEvents.length === 0) {
        return (
            <div className="mt-10 mb-6">
                <div className="flex items-center justify-between mb-3">
                    <h2 className="text-lg font-semibold text-gray-700 flex items-center gap-2">
                        <BellIcon className="w-5 h-5 text-gray-500" />
                        最新イベント
                    </h2>
                    <label className="flex items-center gap-1.5 text-sm text-gray-500 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={showAll}
                            onChange={(e) => setShowAll(e.target.checked)}
                            className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        />
                        全て
                    </label>
                </div>
                <div className="p-6 bg-gray-50 border border-gray-200 rounded-xl text-center">
                    <BellIcon className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                    <p className="text-gray-500 text-sm">まだイベントはありません</p>
                    <p className="text-gray-400 text-xs mt-1">
                        価格変動や在庫復活があると、ここに表示されます
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div className="mt-10 mb-6">
            <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold text-gray-700 flex items-center gap-2">
                    <BellIcon className="w-5 h-5 text-gray-500" />
                    最新イベント
                    <span className="text-sm font-normal text-gray-400">({filteredEvents.length}件)</span>
                </h2>
                <label className="flex items-center gap-1.5 text-sm text-gray-500 cursor-pointer">
                    <input
                        type="checkbox"
                        checked={showAll}
                        onChange={(e) => setShowAll(e.target.checked)}
                        className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                    全て
                </label>
            </div>
            <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                <table className="w-full">
                    <tbody className="divide-y divide-gray-100">
                        {filteredEvents.map((event) => {
                            const config = EVENT_CONFIG[event.event_type] || EVENT_CONFIG.price_drop;
                            const IconComponent = config.Icon;

                            return (
                                <tr
                                    key={event.id}
                                    className={`${config.bgColor} hover:brightness-95 transition-all duration-150`}
                                >
                                    {/* サムネイル */}
                                    <td className="w-16 p-2">
                                        <a
                                            href={event.url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="block"
                                        >
                                            {event.thumb_url ? (
                                                <img
                                                    src={event.thumb_url}
                                                    alt={event.item_name}
                                                    className="w-12 h-12 object-cover rounded-lg"
                                                />
                                            ) : (
                                                <div className="w-12 h-12 bg-gray-200 rounded-lg flex items-center justify-center">
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
                                        </a>
                                    </td>

                                    {/* イベントタイプ */}
                                    <td className="w-28 px-2 py-2">
                                        <span
                                            className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-semibold ${config.textColor} bg-white/60 border ${config.borderColor}`}
                                        >
                                            <IconComponent className={`w-3.5 h-3.5 ${config.iconColor}`} />
                                            {config.label}
                                        </span>
                                    </td>

                                    {/* 商品名 */}
                                    <td className="px-2 py-2">
                                        <a
                                            href={event.url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="block hover:underline"
                                        >
                                            <p className="text-sm text-gray-800 font-medium line-clamp-2">
                                                {event.item_name}
                                            </p>
                                            <p className="text-xs text-gray-500 mt-0.5">{event.store}</p>
                                        </a>
                                    </td>

                                    {/* 価格情報 */}
                                    <td className="w-40 px-2 py-2 text-right">
                                        {event.price !== null && (
                                            <div className="flex flex-col items-end">
                                                <span className={`text-sm font-bold ${config.textColor}`}>
                                                    {formatPrice(event.price)}
                                                </span>
                                                {event.old_price !== null && (
                                                    <div className="flex items-center gap-1 text-xs text-gray-400">
                                                        <span className="line-through">
                                                            {formatPrice(event.old_price)}
                                                        </span>
                                                        {event.old_price > event.price && (
                                                            <span className="text-rose-500 font-medium">
                                                                -
                                                                {(
                                                                    ((event.old_price - event.price) /
                                                                        event.old_price) *
                                                                    100
                                                                ).toFixed(0)}
                                                                %
                                                            </span>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </td>

                                    {/* 時間 */}
                                    <td className="w-20 px-2 py-2 text-right">
                                        <span className="text-xs text-gray-400">
                                            {formatTimeAgo(event.created_at)}
                                        </span>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
