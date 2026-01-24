import {
    CheckCircleIcon,
    XCircleIcon,
    ClockIcon,
    ArrowTopRightOnSquareIcon,
    BuildingStorefrontIcon,
} from "@heroicons/react/24/outline";
import dayjs from "dayjs";
import clsx from "clsx";
import type { Item, StoreEntry } from "../types";
import PriceChart from "./PriceChart";

interface ItemCardProps {
    item: Item;
}

function StoreRow({ store, isBest }: { store: StoreEntry; isBest: boolean }) {
    const isInStock = store.stock > 0;

    return (
        <div
            className={clsx(
                "flex items-center justify-between py-2 px-3 rounded-md",
                isBest ? "bg-blue-50 border border-blue-200" : "bg-gray-50"
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
                {isBest && (
                    <span className="text-xs px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded whitespace-nowrap">
                        最安
                    </span>
                )}
            </div>
            <div className="flex items-center gap-2">
                <div className="text-right">
                    <span className="text-sm font-semibold text-gray-900">
                        {store.effective_price.toLocaleString()}円
                    </span>
                    {store.point_rate > 0 && (
                        <span className="text-xs text-gray-500 ml-1">(実質・{store.point_rate}%還元)</span>
                    )}
                </div>
                <span
                    className={clsx(
                        "flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded-full",
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

export default function ItemCard({ item }: ItemCardProps) {
    // 最安ストアを取得
    const bestStore = item.stores.find((s) => s.store === item.best_store) || item.stores[0];
    const otherStores = item.stores.filter((s) => s.store !== item.best_store);

    // 最終更新日時（最新のものを使用）
    const lastUpdated = item.stores.reduce((latest, store) => {
        return store.last_updated > latest ? store.last_updated : latest;
    }, item.stores[0].last_updated);

    return (
        <div className="bg-white rounded-lg shadow-md border border-gray-200 overflow-hidden">
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
                            <span className="text-lg font-bold text-gray-900">
                                {item.best_effective_price.toLocaleString()}円
                            </span>
                            <span className="text-xs text-gray-500">({item.stores.length}店舗)</span>
                        </div>
                    </div>
                </div>

                {/* ストア一覧 */}
                <div className="mt-4 space-y-2">
                    <StoreRow store={bestStore} isBest={true} />
                    {otherStores.map((store) => (
                        <StoreRow key={store.url_hash} store={store} isBest={false} />
                    ))}
                </div>
            </div>

            {/* グラフ */}
            <div className="px-4 pb-4">
                <PriceChart stores={item.stores} />
            </div>

            <div className="px-4 py-2 bg-gray-50 border-t border-gray-100 flex items-center gap-1 text-xs text-gray-500">
                <ClockIcon className="h-3.5 w-3.5" />
                <span>最終更新: {dayjs(lastUpdated).format("YYYY/MM/DD HH:mm")}</span>
            </div>
        </div>
    );
}
