import { ClockIcon } from "@heroicons/react/24/outline";
import dayjs from "dayjs";
import type { Item, StoreDefinition, Period } from "../types";
import LazyPriceChart from "./LazyPriceChart";
import StoreRow from "./StoreRow";
import { formatPrice } from "../utils/formatPrice";

interface ItemCardProps {
    item: Item;
    storeDefinitions: StoreDefinition[];
    onClick?: (item: Item) => void;
    period?: Period;
}

export default function ItemCard({ item, storeDefinitions, onClick, period = "30" }: ItemCardProps) {
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

    // 最安ストアの通貨単位を取得
    const bestStore = item.stores.find((s) => s.store === item.best_store);
    const priceUnit = bestStore?.price_unit ?? "円";

    const handleClick = () => {
        if (onClick) {
            onClick(item);
        }
    };

    return (
        <div
            className="bg-white rounded-lg shadow-md border border-gray-200 overflow-hidden flex flex-col h-full cursor-pointer hover:shadow-lg hover:border-blue-300 transition-all duration-200"
            onClick={handleClick}
        >
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
                                    {formatPrice(item.best_effective_price!, priceUnit)}
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
                            key={store.item_key}
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
                    <LazyPriceChart stores={item.stores} storeDefinitions={storeDefinitions} period={period} />
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
