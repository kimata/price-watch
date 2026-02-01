import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { ArrowLeftIcon, ClockIcon, ChartBarIcon, ListBulletIcon, CalculatorIcon, BuildingStorefrontIcon } from "@heroicons/react/24/outline";
import dayjs from "dayjs";

// X (Twitter) のカスタムアイコン
function XIcon({ className }: { className?: string }) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="currentColor">
            <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
        </svg>
    );
}
import type { Item, StoreDefinition, Period, Event, StoreEntry, PriceHistoryPoint } from "../types";
import PeriodSelector from "./PeriodSelector";
import PriceChart from "./PriceChart";
import StoreRow from "./StoreRow";
import EventHistory from "./EventHistory";
import LoadingSpinner from "./LoadingSpinner";
import Footer from "./Footer";
import PermalinkHeading from "./PermalinkHeading";
import { fetchItems, fetchItemEvents, fetchItemHistory } from "../services/apiService";
import { formatPrice } from "../utils/formatPrice";

// SSE イベントタイプ
const SSE_EVENT_CONTENT = "content";

interface ItemDetailPageProps {
    item: Item;
    storeDefinitions: StoreDefinition[];
    period: Period;
    onBack: () => void;
    onPeriodChange: (period: Period) => void;
    checkIntervalSec?: number;
    onConfigClick?: (itemName: string) => void;
    onPriceRecordEditorClick?: (store: StoreEntry) => void;
}

export default function ItemDetailPage({
    item: initialItem,
    storeDefinitions,
    period,
    onBack,
    onPeriodChange,
    checkIntervalSec = 1800,
    onConfigClick,
    onPriceRecordEditorClick,
}: ItemDetailPageProps) {
    const [item, setItem] = useState<Item>(initialItem);
    const [events, setEvents] = useState<Event[]>([]);
    const [loadingEvents, setLoadingEvents] = useState(true);
    const [loadingItem, setLoadingItem] = useState(false);

    // SSE 接続用 refs
    const eventSourceRef = useRef<EventSource | null>(null);
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // ストアを実質価格の安い順にソート
    const sortedStores = useMemo(() => {
        return [...item.stores].sort((a, b) => {
            const aPrice = a.effective_price;
            const bPrice = b.effective_price;
            if (aPrice === null && bPrice === null) return 0;
            if (aPrice === null) return 1;
            if (bPrice === null) return -1;
            return aPrice - bPrice;
        });
    }, [item.stores]);

    // 最終更新日時
    const lastUpdated = useMemo(() => {
        const validUpdates = item.stores.filter((s) => s.last_updated);
        if (validUpdates.length === 0) return null;
        return validUpdates.reduce((latest, store) => {
            return store.last_updated > latest ? store.last_updated : latest;
        }, validUpdates[0].last_updated);
    }, [item.stores]);

    // 価格統計
    const priceStats = useMemo(() => {
        const allPrices: number[] = [];
        let dataCount = 0;
        const minByTime = new Map<string, number>();
        item.stores.forEach((store) => {
            store.history.forEach((h) => {
                dataCount++;
                if (h.effective_price !== null) {
                    allPrices.push(h.effective_price);
                    const existing = minByTime.get(h.time);
                    if (existing === undefined || h.effective_price < existing) {
                        minByTime.set(h.time, h.effective_price);
                    }
                }
            });
        });
        const minValues = Array.from(minByTime.values());
        const averagePrice =
            minValues.length > 0
                ? Math.round(minValues.reduce((sum, price) => sum + price, 0) / minValues.length)
                : null;
        return {
            lowestPrice: allPrices.length > 0 ? Math.min(...allPrices) : null,
            highestPrice: allPrices.length > 0 ? Math.max(...allPrices) : null,
            averagePrice,
            dataCount,
        };
    }, [item.stores]);

    const lastUpdatedRelative = useMemo(() => {
        if (!lastUpdated) return "未取得";
        const diffMinutes = dayjs().diff(dayjs(lastUpdated), "minute");
        if (diffMinutes < 60) return `${diffMinutes}分前`;
        const diffHours = dayjs().diff(dayjs(lastUpdated), "hour");
        if (diffHours < 24) return `${diffHours}時間前`;
        const diffDays = dayjs().diff(dayjs(lastUpdated), "day");
        if (diffDays < 30) return `${diffDays}日前`;
        return dayjs(lastUpdated).format("YYYY年M月D日");
    }, [lastUpdated]);

    // アイテム情報を期間変更時に再取得（履歴も含む）
    const loadItemData = useCallback(async () => {
        setLoadingItem(true);
        try {
            // アイテム一覧を取得（履歴なし）
            const response = await fetchItems(period);
            const foundItem = response.items.find((i) => i.name === item.name);
            if (foundItem) {
                // 各ストアの履歴を並列で取得
                const storesWithHistory = await Promise.all(
                    foundItem.stores.map(async (store): Promise<StoreEntry> => {
                        try {
                            const historyResponse = await fetchItemHistory(store.item_key, period);
                            return {
                                ...store,
                                history: historyResponse.history,
                            };
                        } catch {
                            // 個別のエラーは無視して空の履歴を返す
                            return {
                                ...store,
                                history: [] as PriceHistoryPoint[],
                            };
                        }
                    })
                );
                setItem({
                    ...foundItem,
                    stores: storesWithHistory,
                });
            }
        } catch (err) {
            console.error("Failed to load item data:", err);
        } finally {
            setLoadingItem(false);
        }
    }, [period, item.name]);

    // イベント履歴を取得
    const loadEvents = useCallback(async () => {
        setLoadingEvents(true);
        try {
            // 全ストアのイベントを取得してマージ
            const allEvents: Event[] = [];
            for (const store of item.stores) {
                const response = await fetchItemEvents(store.item_key, 20);
                allEvents.push(...response.events);
            }
            // 日時でソート（新しい順）
            allEvents.sort((a, b) => dayjs(b.created_at).valueOf() - dayjs(a.created_at).valueOf());
            // 重複を除去（同じIDのイベント）
            const uniqueEvents = allEvents.filter(
                (event, index, self) => self.findIndex((e) => e.id === event.id) === index
            );
            setEvents(uniqueEvents.slice(0, 50));
        } catch (err) {
            console.error("Failed to load events:", err);
        } finally {
            setLoadingEvents(false);
        }
    }, [item.stores]);

    // 期間変更時にアイテムデータを再取得
    useEffect(() => {
        loadItemData();
    }, [loadItemData]);

    // 初回ロード時にイベントを取得
    useEffect(() => {
        loadEvents();
    }, [loadEvents]);

    // SSE 接続（コンテンツ更新イベントを受信）
    useEffect(() => {
        const connectSSE = () => {
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
            }

            const eventSource = new EventSource("/price/api/event");

            eventSource.onmessage = (event) => {
                if (event.data === SSE_EVENT_CONTENT) {
                    loadItemData();
                    loadEvents();
                }
            };

            eventSource.onerror = () => {
                eventSource.close();
                // 5秒後に再接続
                reconnectTimerRef.current = setTimeout(() => {
                    connectSSE();
                }, 5000);
            };

            eventSourceRef.current = eventSource;
        };

        connectSSE();

        return () => {
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
            }
            if (reconnectTimerRef.current) {
                clearTimeout(reconnectTimerRef.current);
            }
        };
    }, [loadItemData, loadEvents]);

    const hasValidPrice = item.best_effective_price !== null;

    // 最安ストアの通貨単位を取得
    const bestStoreEntry = item.stores.find((s) => s.store === item.best_store);
    const priceUnit = bestStoreEntry?.price_unit ?? "円";

    return (
        <div className="min-h-screen bg-gray-100">
            {/* 戻るボタン */}
            <div className="sticky top-0 z-10 bg-white border-b border-gray-200 shadow-sm">
                <div className="max-w-4xl mx-auto px-4 py-3">
                    <button
                        onClick={onBack}
                        className="cursor-pointer flex items-center gap-2 text-gray-600 hover:text-blue-600 transition-colors"
                    >
                        <ArrowLeftIcon className="h-5 w-5" />
                        <span className="text-sm font-medium">一覧に戻る</span>
                    </button>
                </div>
            </div>

            <main className="max-w-4xl mx-auto px-4 py-6">
                {/* ヘッダー: サムネイル + 基本情報 */}
                <div className="bg-white rounded-lg shadow-md border border-gray-200 p-6 mb-6">
                    <div className="flex gap-6">
                        {item.thumb_url ? (
                            <img
                                src={item.thumb_url}
                                alt={item.name}
                                className="w-32 h-32 object-cover rounded-lg flex-shrink-0"
                            />
                        ) : (
                            <div className="w-32 h-32 bg-gray-100 rounded-lg flex-shrink-0 flex items-center justify-center">
                                <span className="text-gray-400 text-sm">No Image</span>
                            </div>
                        )}
                        <div className="flex-1 min-w-0 flex flex-col">
                            <h1 className="text-xl font-bold text-gray-900 mb-2">{item.name}</h1>
                            <div className="flex items-baseline gap-2 mb-2">
                                {hasValidPrice ? (
                                    <>
                                        <span className="text-3xl font-bold text-gray-900">
                                            {formatPrice(item.best_effective_price!, priceUnit)}
                                        </span>
                                        <span className="text-sm text-gray-500">
                                            ({item.best_store}が最安)
                                        </span>
                                    </>
                                ) : (
                                    <span className="text-2xl text-gray-400">価格情報なし</span>
                                )}
                            </div>
                            <div className="flex-1" />
                            <div className="flex items-center justify-between">
                            <div className="flex items-center gap-1 text-sm text-gray-500">
                                <ClockIcon className="h-4 w-4" />
                                <span>
                                        最終更新: {lastUpdated ? dayjs(lastUpdated).format("YYYY年M月D日 HH:mm") : "未取得"}
                                        {lastUpdated ? ` (${lastUpdatedRelative})` : ""}
                                    </span>
                                </div>
                                <a
                                    href={`https://twitter.com/intent/tweet?text=${encodeURIComponent(
                                        hasValidPrice
                                            ? `${item.name} 最安値 ${formatPrice(item.best_effective_price!, priceUnit)} (${item.best_store})`
                                            : item.name
                                    )}&url=${encodeURIComponent(window.location.href)}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="flex items-center gap-1 px-2 py-1 text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded transition-colors"
                                    title="X (Twitter) で共有"
                                >
                                    <XIcon className="h-4 w-4" />
                                </a>
                            </div>
                        </div>
                    </div>
                </div>

                {/* 期間セレクタ */}
                <div className="mb-6">
                    <PeriodSelector selected={period} onChange={onPeriodChange} />
                </div>

                {/* 価格統計 */}
                <div className="bg-white rounded-lg shadow-md border border-gray-200 p-6 mb-6">
                    <PermalinkHeading
                        id="price-stats"
                        className="text-lg font-semibold text-gray-700 mb-4"
                    >
                        <CalculatorIcon className="h-5 w-5" />
                        価格統計
                    </PermalinkHeading>
                    <div className="grid grid-cols-3 gap-4">
                        <div className="text-center p-4 bg-green-50 rounded-lg border border-green-100">
                            <div className="text-sm text-gray-600 mb-2">期間内最安値</div>
                            <div className="text-2xl font-bold text-green-600">
                                {priceStats.lowestPrice !== null
                                    ? formatPrice(priceStats.lowestPrice, priceUnit)
                                    : "-"}
                            </div>
                        </div>
                        <div className="text-center p-4 bg-red-50 rounded-lg border border-red-100">
                            <div className="text-sm text-gray-600 mb-2">期間内最高値</div>
                            <div className="text-2xl font-bold text-red-600">
                                {priceStats.highestPrice !== null
                                    ? formatPrice(priceStats.highestPrice, priceUnit)
                                    : "-"}
                            </div>
                        </div>
                        <div className="text-center p-4 bg-gray-50 rounded-lg">
                            <div className="text-sm text-gray-600 mb-2">期間内最安値平均</div>
                            <div className="text-xl font-semibold text-gray-600">
                                {priceStats.averagePrice !== null
                                    ? formatPrice(priceStats.averagePrice, priceUnit)
                                    : "-"}
                            </div>
                        </div>
                    </div>
                    <div className="mt-4 text-sm text-gray-500">
                        データポイント数: {priceStats.dataCount}
                    </div>
                </div>

                {/* 価格チャート（拡大版） */}
                <div className="bg-white rounded-lg shadow-md border border-gray-200 p-6 mb-6">
                    <PermalinkHeading
                        id="price-chart"
                        className="text-lg font-semibold text-gray-700 mb-4"
                    >
                        <ChartBarIcon className="h-5 w-5" />
                        価格推移
                    </PermalinkHeading>
                    {loadingItem ? (
                        <div className="h-72 flex items-center justify-center">
                            <LoadingSpinner />
                        </div>
                    ) : (
                        <PriceChart stores={item.stores} storeDefinitions={storeDefinitions} className="h-72" period={period} largeLabels checkIntervalSec={checkIntervalSec} />
                    )}
                </div>

                {/* ストア別現在価格 */}
                <div className="bg-white rounded-lg shadow-md border border-gray-200 p-6 mb-6">
                    <PermalinkHeading
                        id="store-prices"
                        className="text-lg font-semibold text-gray-700 mb-4"
                    >
                        <BuildingStorefrontIcon className="h-5 w-5" />
                        ストア別現在価格
                    </PermalinkHeading>
                    <div className="space-y-2">
                        {sortedStores.map((store) => (
                            <StoreRow
                                key={store.item_key}
                                store={store}
                                isBest={store.store === item.best_store}
                                bestPrice={item.best_effective_price}
                                onEditClick={onPriceRecordEditorClick}
                            />
                        ))}
                    </div>
                </div>

                {/* イベント履歴 */}
                <div className="bg-white rounded-lg shadow-md border border-gray-200 p-6">
                    <PermalinkHeading
                        id="event-history"
                        className="text-lg font-semibold text-gray-700 mb-4"
                    >
                        <ListBulletIcon className="h-5 w-5" />
                        イベント履歴
                    </PermalinkHeading>
                    {loadingEvents ? (
                        <div className="flex justify-center py-8">
                            <LoadingSpinner />
                        </div>
                    ) : (
                        <EventHistory events={events} />
                    )}
                </div>
            </main>
            <Footer storeDefinitions={storeDefinitions} onConfigClick={onConfigClick ? () => onConfigClick(item.name) : undefined} />
        </div>
    );
}
