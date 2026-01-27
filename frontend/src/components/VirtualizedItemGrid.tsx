import type { Item, StoreDefinition, Period } from "../types";
import ItemCard from "./ItemCard";

interface VirtualizedItemGridProps {
    items: Item[];
    storeDefinitions: StoreDefinition[];
    onItemClick: (item: Item) => void;
    period: Period;
}

/**
 * アイテムグリッド
 *
 * LazyPriceChart を使用しているため、各カードのグラフは
 * ビューポート内に入ったときに遅延読み込みされます。
 * これにより、100以上のアイテムがあっても初期ロードは高速です。
 */
export default function VirtualizedItemGrid({
    items,
    storeDefinitions,
    onItemClick,
    period,
}: VirtualizedItemGridProps) {
    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {items.map((item) => (
                <ItemCard
                    key={item.name}
                    item={item}
                    storeDefinitions={storeDefinitions}
                    onClick={onItemClick}
                    period={period}
                />
            ))}
        </div>
    );
}
