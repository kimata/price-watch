import { useState, useEffect, useCallback, useMemo } from "react";
import { ArrowLeftIcon, ClockIcon, ChartBarIcon, ListBulletIcon } from "@heroicons/react/24/outline";
import dayjs from "dayjs";
import type { Item, StoreDefinition, Period, Event } from "../types";
import PeriodSelector from "./PeriodSelector";
import PriceChart from "./PriceChart";
import StoreRow from "./StoreRow";
import EventHistory from "./EventHistory";
import LoadingSpinner from "./LoadingSpinner";
import { fetchItems, fetchItemEvents } from "../services/apiService";

interface ItemDetailPageProps {
    item: Item;
    storeDefinitions: StoreDefinition[];
    period: Period;
    onBack: () => void;
    onPeriodChange: (period: Period) => void;
}

export default function ItemDetailPage({
    item: initialItem,
    storeDefinitions,
    period,
    onBack,
    onPeriodChange,
}: ItemDetailPageProps) {
    const [item, setItem] = useState<Item>(initialItem);
    const [events, setEvents] = useState<Event[]>([]);
    const [loadingEvents, setLoadingEvents] = useState(true);
    const [loadingItem, setLoadingItem] = useState(false);

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
        item.stores.forEach((store) => {
            store.history.forEach((h) => {
                dataCount++;
                if (h.effective_price !== null) {
                    allPrices.push(h.effective_price);
                }
            });
        });
        return {
            lowestPrice: allPrices.length > 0 ? Math.min(...allPrices) : null,
            highestPrice: allPrices.length > 0 ? Math.max(...allPrices) : null,
            dataCount,
        };
    }, [item.stores]);

    // アイテム情報を期間変更時に再取得
    const loadItemData = useCallback(async () => {
        setLoadingItem(true);
        try {
            const response = await fetchItems(period);
            const foundItem = response.items.find((i) => i.name === item.name);
            if (foundItem) {
                setItem(foundItem);
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

    const hasValidPrice = item.best_effective_price !== null;

    return (
        <div className="min-h-screen bg-gray-100">
            {/* 戻るボタン */}
            <div className="sticky top-0 z-10 bg-white border-b border-gray-200 shadow-sm">
                <div className="max-w-4xl mx-auto px-4 py-3">
                    <button
                        onClick={onBack}
                        className="flex items-center gap-2 text-gray-600 hover:text-blue-600 transition-colors"
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
                        <div className="flex-1 min-w-0">
                            <h1 className="text-xl font-bold text-gray-900 mb-2">{item.name}</h1>
                            <div className="flex items-baseline gap-2 mb-2">
                                {hasValidPrice ? (
                                    <>
                                        <span className="text-3xl font-bold text-gray-900">
                                            {item.best_effective_price!.toLocaleString()}円
                                        </span>
                                        <span className="text-sm text-gray-500">
                                            ({item.best_store}が最安)
                                        </span>
                                    </>
                                ) : (
                                    <span className="text-2xl text-gray-400">価格情報なし</span>
                                )}
                            </div>
                            <div className="flex items-center gap-1 text-sm text-gray-500">
                                <ClockIcon className="h-4 w-4" />
                                <span>
                                    最終更新: {lastUpdated ? dayjs(lastUpdated).format("YYYY年M月D日 HH:mm") : "未取得"}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* 期間セレクタ */}
                <div className="mb-6">
                    <PeriodSelector selected={period} onChange={onPeriodChange} />
                </div>

                {/* 価格チャート（拡大版） */}
                <div className="bg-white rounded-lg shadow-md border border-gray-200 p-6 mb-6">
                    <h2 className="text-lg font-semibold text-gray-700 mb-4 flex items-center gap-2">
                        <ChartBarIcon className="h-5 w-5" />
                        価格推移
                    </h2>
                    {loadingItem ? (
                        <div className="h-72 flex items-center justify-center">
                            <LoadingSpinner />
                        </div>
                    ) : (
                        <PriceChart stores={item.stores} storeDefinitions={storeDefinitions} className="h-72" />
                    )}
                </div>

                {/* 価格統計 */}
                <div className="bg-white rounded-lg shadow-md border border-gray-200 p-6 mb-6">
                    <h2 className="text-lg font-semibold text-gray-700 mb-4">価格統計</h2>
                    <div className="grid grid-cols-3 gap-4">
                        <div className="text-center p-4 bg-gray-50 rounded-lg">
                            <div className="text-sm text-gray-500 mb-1">期間内最安値</div>
                            <div className="text-lg font-bold text-green-600">
                                {priceStats.lowestPrice !== null
                                    ? `${priceStats.lowestPrice.toLocaleString()}円`
                                    : "-"}
                            </div>
                        </div>
                        <div className="text-center p-4 bg-gray-50 rounded-lg">
                            <div className="text-sm text-gray-500 mb-1">期間内最高値</div>
                            <div className="text-lg font-bold text-red-600">
                                {priceStats.highestPrice !== null
                                    ? `${priceStats.highestPrice.toLocaleString()}円`
                                    : "-"}
                            </div>
                        </div>
                        <div className="text-center p-4 bg-gray-50 rounded-lg">
                            <div className="text-sm text-gray-500 mb-1">データポイント数</div>
                            <div className="text-lg font-bold text-gray-700">
                                {priceStats.dataCount}
                            </div>
                        </div>
                    </div>
                </div>

                {/* ストア別情報 */}
                <div className="bg-white rounded-lg shadow-md border border-gray-200 p-6 mb-6">
                    <h2 className="text-lg font-semibold text-gray-700 mb-4">ストア別価格</h2>
                    <div className="space-y-2">
                        {sortedStores.map((store) => (
                            <StoreRow
                                key={store.item_key}
                                store={store}
                                isBest={store.store === item.best_store}
                                bestPrice={item.best_effective_price}
                            />
                        ))}
                    </div>
                </div>

                {/* イベント履歴 */}
                <div className="bg-white rounded-lg shadow-md border border-gray-200 p-6">
                    <h2 className="text-lg font-semibold text-gray-700 mb-4 flex items-center gap-2">
                        <ListBulletIcon className="h-5 w-5" />
                        イベント履歴
                    </h2>
                    {loadingEvents ? (
                        <div className="flex justify-center py-8">
                            <LoadingSpinner />
                        </div>
                    ) : (
                        <EventHistory events={events} />
                    )}
                </div>
            </main>
        </div>
    );
}
