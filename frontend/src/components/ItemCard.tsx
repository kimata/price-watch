import {
    CheckCircleIcon,
    XCircleIcon,
    ClockIcon,
    ArrowTopRightOnSquareIcon,
    BuildingStorefrontIcon,
} from "@heroicons/react/24/outline";
import dayjs from "dayjs";
import clsx from "clsx";
import type { Item, StoreEntry, StoreDefinition } from "../types";
import PriceChart from "./PriceChart";

interface ItemCardProps {
    item: Item;
    storeDefinitions: StoreDefinition[];
}

function StoreRow({
    store,
    isBest,
    bestPrice,
}: {
    store: StoreEntry;
    isBest: boolean;
    bestPrice: number | null;
}) {
    const isInStock = store.stock > 0;
    const hasPrice = store.effective_price !== null;
    const priceDiff = hasPrice && bestPrice !== null ? store.effective_price! - bestPrice : 0;

    return (
        <div
            className={clsx(
                "flex items-center justify-between py-2 px-3 rounded-md",
                isBest && hasPrice ? "bg-blue-50 border border-blue-200" : "bg-gray-50"
            )}
        >
            <div className="flex items-center gap-2 min-w-0 flex-1">
                <a
                    href={store.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-gray-700 hover:text-blue-600 truncate flex items-center gap-1"
                >
                    <BuildingStorefrontIcon className="h-3.5 w-3.5 flex-shrink-0" />
                    <span className="truncate">{store.store}</span>
                    <ArrowTopRightOnSquareIcon className="h-3 w-3 flex-shrink-0" />
                </a>
                {isBest && hasPrice && (
                    <span className="text-xs px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded whitespace-nowrap">
                        最安
                    </span>
                )}
            </div>
            <div className="flex items-center gap-2">
                <div className="text-right min-w-[5.5rem]">
                    {hasPrice ? (
                        <>
                            <div className="text-sm font-semibold text-gray-900 whitespace-nowrap tabular-nums">
                                {store.effective_price!.toLocaleString()}円
                            </div>
                            {(priceDiff > 0 || store.point_rate > 0) && (
                                <div className="text-xs text-gray-400 whitespace-nowrap">
                                    {priceDiff > 0 && <span>+{priceDiff.toLocaleString()}円</span>}
                                    {priceDiff > 0 && store.point_rate > 0 && <span> / </span>}
                                    {store.point_rate > 0 && <span>{store.point_rate}%還元考慮</span>}
                                </div>
                            )}
                        </>
                    ) : (
                        <div className="text-sm text-gray-400 whitespace-nowrap">---</div>
                    )}
                </div>
                <span
                    className={clsx(
                        "flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded-full flex-shrink-0",
                        isInStock ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                    )}
                >
                    {isInStock ? (
                        <CheckCircleIcon className="h-3 w-3" />
                    ) : (
                        <XCircleIcon className="h-3 w-3" />
                    )}
                </span>
            </div>
        </div>
    );
}

export default function ItemCard({ item, storeDefinitions }: ItemCardProps) {
    // ストアを実質価格の安い順にソート（価格nullのものは後ろに）
    const sortedStores = [...item.stores].sort((a, b) => {
        const aPrice = a.effective_price;
        const bPrice = b.effective_price;
        if (aPrice === null && bPrice === null) return 0;
        if (aPrice === null) return 1;
        if (bPrice === null) return -1;
        return aPrice - bPrice;
    });

    // 最終更新日時（最新のものを使用、空文字は除外）
    const validUpdates = item.stores.filter((s) => s.last_updated);
    const lastUpdated = validUpdates.length > 0
        ? validUpdates.reduce((latest, store) => {
              return store.last_updated > latest ? store.last_updated : latest;
          }, validUpdates[0].last_updated)
        : null;

    // 有効な価格があるかどうか（null でなければ価格あり、0円も有効な価格）
    const hasValidPrice = item.best_effective_price !== null;

    return (
        <div className="bg-white rounded-lg shadow-md border border-gray-200 overflow-hidden flex flex-col h-full">
            <div className="p-4">
                <div className="flex gap-4">
                    {item.thumb_url ? (
                        <img
                            src={item.thumb_url}
                            alt={item.name}
                            className="w-20 h-20 object-cover rounded-md flex-shrink-0"
                        />
                    ) : (
                        <div className="w-20 h-20 bg-gray-100 rounded-md flex-shrink-0 flex items-center justify-center">
                            <span className="text-gray-400 text-xs">No Image</span>
                        </div>
                    )}
                    <div className="flex-1 min-w-0">
                        <h3 className="text-sm font-semibold text-gray-900 line-clamp-2">{item.name}</h3>
                        <div className="flex items-center gap-2 mt-2">
                            {hasValidPrice ? (
                                <span className="text-lg font-bold text-gray-900">
                                    {item.best_effective_price!.toLocaleString()}円
                                </span>
                            ) : (
                                <span className="text-lg text-gray-400">---</span>
                            )}
                            <span className="text-xs text-gray-500">({item.stores.length}店舗)</span>
                        </div>
                    </div>
                </div>

                {/* ストア一覧（価格順） */}
                <div className="mt-4 space-y-2">
                    {sortedStores.map((store) => (
                        <StoreRow
                            key={store.url_hash}
                            store={store}
                            isBest={store.store === item.best_store}
                            bestPrice={item.best_effective_price}
                        />
                    ))}
                </div>
            </div>

            {/* グラフと最終更新を下部に配置 */}
            <div className="mt-auto">
                <div className="px-4 pb-4">
                    <PriceChart stores={item.stores} storeDefinitions={storeDefinitions} />
                </div>

                <div className="px-4 py-2 bg-gray-50 border-t border-gray-100 flex items-center gap-1 text-xs text-gray-500">
                    <ClockIcon className="h-3.5 w-3.5" />
                    <span>
                        最終更新: {lastUpdated ? dayjs(lastUpdated).format("YYYY年M月D日 HH:mm") : "未取得"}
                    </span>
                </div>
            </div>
        </div>
    );
}
