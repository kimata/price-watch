import clsx from "clsx";
import dayjs from "dayjs";
import type { Event, EventType } from "../types";

interface EventHistoryProps {
    events: Event[];
}

const EVENT_CONFIG: Record<
    EventType,
    {
        emoji: string;
        bgColor: string;
        textColor: string;
        label: string;
    }
> = {
    back_in_stock: {
        emoji: "📦",
        bgColor: "bg-emerald-100",
        textColor: "text-emerald-700",
        label: "在庫復活",
    },
    crawl_failure: {
        emoji: "⚠️",
        bgColor: "bg-amber-100",
        textColor: "text-amber-700",
        label: "取得失敗",
    },
    lowest_price: {
        emoji: "🔥",
        bgColor: "bg-rose-100",
        textColor: "text-rose-700",
        label: "最安値更新",
    },
    price_drop: {
        emoji: "📉",
        bgColor: "bg-sky-100",
        textColor: "text-sky-700",
        label: "値下げ",
    },
};

function formatPrice(price: number | null): string {
    if (price === null) return "-";
    return price.toLocaleString("ja-JP") + "円";
}

export default function EventHistory({ events }: EventHistoryProps) {
    if (events.length === 0) {
        return (
            <div className="p-6 bg-gray-50 border border-gray-200 rounded-lg text-center">
                <span className="text-2xl mb-2 block">📭</span>
                <p className="text-gray-500 text-sm">イベント履歴はありません</p>
            </div>
        );
    }

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-sm">
                <thead>
                    <tr className="border-b border-gray-200">
                        <th className="text-left py-2 px-3 font-medium text-gray-600">日時</th>
                        <th className="text-left py-2 px-3 font-medium text-gray-600">ストア</th>
                        <th className="text-left py-2 px-3 font-medium text-gray-600">イベント</th>
                        <th className="text-right py-2 px-3 font-medium text-gray-600">価格変動</th>
                    </tr>
                </thead>
                <tbody>
                    {events.map((event) => {
                        const config = EVENT_CONFIG[event.event_type] || EVENT_CONFIG.price_drop;

                        return (
                            <tr key={event.id} className="border-b border-gray-100 hover:bg-gray-50">
                                <td className="py-2 px-3 text-gray-600 whitespace-nowrap">
                                    {dayjs(event.created_at).format("YYYY年M月D日 H:mm")}
                                </td>
                                <td className="py-2 px-3 text-gray-700">
                                    {event.store}
                                </td>
                                <td className="py-2 px-3">
                                    <span
                                        className={clsx(
                                            "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium",
                                            config.bgColor,
                                            config.textColor
                                        )}
                                    >
                                        <span>{config.emoji}</span>
                                        {config.label}
                                    </span>
                                </td>
                                <td className="py-2 px-3 text-right whitespace-nowrap">
                                    {event.old_price !== null && event.price !== null ? (
                                        <span className="text-gray-600">
                                            <span className="line-through text-gray-400 mr-1">
                                                {formatPrice(event.old_price)}
                                            </span>
                                            →
                                            <span className="ml-1 font-medium">
                                                {formatPrice(event.price)}
                                            </span>
                                            {event.old_price > event.price && (
                                                <span className="ml-1 text-xs text-rose-500">
                                                    -{((event.old_price - event.price) / event.old_price * 100).toFixed(0)}%
                                                </span>
                                            )}
                                        </span>
                                    ) : event.price !== null ? (
                                        <span className="font-medium">{formatPrice(event.price)}</span>
                                    ) : (
                                        <span className="text-gray-400">-</span>
                                    )}
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}
