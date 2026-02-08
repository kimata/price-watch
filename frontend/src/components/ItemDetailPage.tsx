import { useMemo } from "react";
import { ArrowLeftIcon, ClockIcon, ChartBarIcon, ListBulletIcon, CalculatorIcon, BuildingStorefrontIcon } from "@heroicons/react/24/outline";
import dayjs from "dayjs";
import type { Item, StoreDefinition, Period } from "../types";
import PeriodSelector from "./PeriodSelector";
import PriceChart from "./PriceChart";
import StoreRow from "./StoreRow";
import EventHistory from "./EventHistory";
import LoadingSpinner from "./LoadingSpinner";
import Footer from "./Footer";
import PermalinkHeading from "./PermalinkHeading";
import FavoriteButton from "./FavoriteButton";
import ShareButtons from "./ShareButtons";
import { ChartSkeleton } from "./skeletons";
import { useItemDetails, useItemEvents } from "../hooks/useItems";
import { formatPrice } from "../utils/formatPrice";

interface ItemDetailPageProps {
    item: Item;
    storeDefinitions: StoreDefinition[];
    period: Period;
    onBack: () => void;
    onPeriodChange: (period: Period) => void;
    checkIntervalSec?: number;
    onConfigClick?: (itemName: string) => void;
    onPriceRecordEditorClick?: () => void;
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
    // TanStack Query でアイテム詳細を取得（SSE更新も自動で反映）
    const { data: item, isLoading: loadingItem } = useItemDetails(initialItem, period);

    // 表示するアイテム（取得中は初期アイテムを使用）
    const displayItem = item ?? initialItem;

    // TanStack Query でイベント履歴を取得
    const { data: events = [], isLoading: loadingEvents } = useItemEvents(displayItem.stores);

    // ストアを実質価格の安い順にソート
    const sortedStores = useMemo(() => {
        return [...displayItem.stores].sort((a, b) => {
            const aPrice = a.effective_price;
            const bPrice = b.effective_price;
            if (aPrice === null && bPrice === null) return 0;
            if (aPrice === null) return 1;
            if (bPrice === null) return -1;
            return aPrice - bPrice;
        });
    }, [displayItem.stores]);

    // 最終更新日時
    const lastUpdated = useMemo(() => {
        const validUpdates = displayItem.stores.filter((s) => s.last_updated);
        if (validUpdates.length === 0) return null;
        return validUpdates.reduce((latest, store) => {
            return store.last_updated > latest ? store.last_updated : latest;
        }, validUpdates[0].last_updated);
    }, [displayItem.stores]);

    // 価格統計
    const priceStats = useMemo(() => {
        const allPrices: number[] = [];
        let dataCount = 0;
        const minByTime = new Map<string, number>();
        displayItem.stores.forEach((store) => {
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
    }, [displayItem.stores]);

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

    const hasValidPrice = displayItem.best_effective_price !== null;

    // 最安ストアの通貨単位を取得
    const bestStoreEntry = displayItem.stores.find((s) => s.store === displayItem.best_store);
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
                        {displayItem.thumb_url ? (
                            <img
                                src={displayItem.thumb_url}
                                alt={displayItem.name}
                                className="w-32 h-32 object-cover rounded-lg flex-shrink-0"
                            />
                        ) : (
                            <div className="w-32 h-32 bg-gray-100 rounded-lg flex-shrink-0 flex items-center justify-center">
                                <span className="text-gray-400 text-sm">No Image</span>
                            </div>
                        )}
                        <div className="flex-1 min-w-0 flex flex-col">
                            <div className="flex items-start justify-between gap-2 mb-2">
                                <h1 className="text-xl font-bold text-gray-900">{displayItem.name}</h1>
                                <FavoriteButton itemName={displayItem.name} size="lg" />
                            </div>
                            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0 mb-2">
                                {hasValidPrice ? (
                                    <>
                                        <span className="text-3xl font-bold text-gray-900 whitespace-nowrap">
                                            {formatPrice(displayItem.best_effective_price!, priceUnit)}
                                        </span>
                                        <span className="text-sm text-gray-500 whitespace-nowrap">
                                            ({displayItem.best_store}が最安)
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
                                <ShareButtons
                                    title={displayItem.name}
                                    text={
                                        hasValidPrice
                                            ? `${displayItem.name} 最安値 ${formatPrice(displayItem.best_effective_price!, priceUnit)} (${displayItem.best_store})`
                                            : displayItem.name
                                    }
                                />
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
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                        <div className="text-center p-4 bg-green-50 rounded-lg border border-green-100">
                            <div className="text-sm text-gray-600 mb-2">期間内最安値</div>
                            <div className="text-xl sm:text-2xl font-bold text-green-600 whitespace-nowrap">
                                {priceStats.lowestPrice !== null
                                    ? formatPrice(priceStats.lowestPrice, priceUnit)
                                    : "-"}
                            </div>
                        </div>
                        <div className="text-center p-4 bg-red-50 rounded-lg border border-red-100">
                            <div className="text-sm text-gray-600 mb-2">期間内最高値</div>
                            <div className="text-xl sm:text-2xl font-bold text-red-600 whitespace-nowrap">
                                {priceStats.highestPrice !== null
                                    ? formatPrice(priceStats.highestPrice, priceUnit)
                                    : "-"}
                            </div>
                        </div>
                        <div className="col-span-2 sm:col-span-1 text-center p-4 bg-gray-50 rounded-lg">
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
                        <ChartSkeleton className="h-72" />
                    ) : (
                        <PriceChart stores={displayItem.stores} storeDefinitions={storeDefinitions} className="h-72" period={period} largeLabels checkIntervalSec={checkIntervalSec} />
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
                                isBest={store.store === displayItem.best_store}
                                bestPrice={displayItem.best_effective_price}
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
            <Footer storeDefinitions={storeDefinitions} onConfigClick={onConfigClick ? () => onConfigClick(displayItem.name) : undefined} onPriceRecordEditorClick={onPriceRecordEditorClick} />
        </div>
    );
}
